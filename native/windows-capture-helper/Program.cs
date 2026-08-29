using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace WindowsCaptureHelper;

internal static class Program
{
    private const int Succeeded = 0;
    private const int InvalidArguments = 2;
    private const int Failure = 1;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false,
    };

    public static int Main(string[] args)
    {
        if (args.Length == 2 &&
            string.Equals(args[0], "doctor", StringComparison.OrdinalIgnoreCase) &&
            string.Equals(args[1], "--json", StringComparison.Ordinal))
        {
            return RunDoctor();
        }

        // Keep stdout machine-readable even for unsupported commands. No usage text,
        // paths, device names, or other diagnostics are written to stdout.
        WriteJson(new DoctorResult
        {
            SchemaVersion = 1,
            Operation = "doctor",
            Ok = false,
            Platform = PlatformInfo.Current(),
            Error = new ErrorInfo
            {
                Code = "invalid_arguments",
                Stage = "command_line",
            },
        });
        return InvalidArguments;
    }

    private static int RunDoctor()
    {
        var result = new DoctorResult
        {
            SchemaVersion = 1,
            Operation = "doctor",
            Ok = false,
            Platform = PlatformInfo.Current(),
            Endpoint = new EndpointInfo
            {
                Flow = "render",
                Role = "console",
                RecordingStarted = false,
            },
        };

        object? enumeratorCom = null;
        object? endpointCom = null;
        object? audioClientCom = null;
        IntPtr mixFormat = IntPtr.Zero;

        try
        {
            if (!OperatingSystem.IsWindows())
            {
                result.Error = new ErrorInfo
                {
                    Code = "windows_required",
                    Stage = "platform",
                };
                WriteJson(result);
                return Failure;
            }

            enumeratorCom = new MmDeviceEnumeratorComObject();
            var enumerator = (IMMDeviceEnumerator)enumeratorCom;

            var endpointHResult = enumerator.GetDefaultAudioEndpoint(
                DataFlow.Render,
                AudioRole.Console,
                out var endpoint);
            EnsureSucceeded(endpointHResult, "IMMDeviceEnumerator.GetDefaultAudioEndpoint");
            endpointCom = endpoint;

            var stateHResult = endpoint.GetState(out var state);
            EnsureSucceeded(stateHResult, "IMMDevice.GetState");
            result.Endpoint!.State = DeviceStateName(state);

            var audioClientIid = typeof(IAudioClient).GUID;
            var activateHResult = endpoint.Activate(
                ref audioClientIid,
                ClsContext.All,
                IntPtr.Zero,
                out var activatedClient);
            EnsureSucceeded(activateHResult, "IMMDevice.Activate");
            audioClientCom = activatedClient;
            var audioClient = (IAudioClient)activatedClient;

            var formatHResult = audioClient.GetMixFormat(out mixFormat);
            EnsureSucceeded(formatHResult, "IAudioClient.GetMixFormat");

            // Initialize the client with LOOPBACK, but deliberately never call
            // Start/GetBuffer. This proves the render endpoint can be opened for
            // WASAPI loopback without recording or retaining audio data.
            var initializeHResult = audioClient.Initialize(
                AudioClientShareMode.Shared,
                AudioClientStreamFlags.Loopback,
                0,
                0,
                mixFormat,
                IntPtr.Zero);

            result.Endpoint.Loopback = new LoopbackInfo
            {
                Supported = initializeHResult >= 0,
                Initialized = initializeHResult >= 0,
                RecordingStarted = false,
            };

            if (initializeHResult < 0)
            {
                result.Endpoint.Loopback.Error = new ErrorInfo
                {
                    Code = "loopback_initialize_failed",
                    Stage = "IAudioClient.Initialize",
                    HResult = FormatHResult(initializeHResult),
                };
            }

            result.Ok = state == AudioDeviceState.Active && initializeHResult >= 0;
            if (!result.Ok && state != AudioDeviceState.Active)
            {
                result.Error = new ErrorInfo
                {
                    Code = "render_endpoint_not_active",
                    Stage = "IMMDevice.GetState",
                };
            }

            WriteJson(result);
            return result.Ok ? Succeeded : Failure;
        }
        catch (CaptureHelperException exception)
        {
            result.Error = exception.Error;
            WriteJson(result);
            return Failure;
        }
        catch (COMException exception)
        {
            // Only expose the HRESULT and fixed stage. COM exception messages can
            // contain implementation-specific details, so they are intentionally
            // excluded from the machine-readable contract.
            result.Error = new ErrorInfo
            {
                Code = "com_call_failed",
                Stage = "core_audio",
                HResult = FormatHResult(exception.HResult),
            };
            WriteJson(result);
            return Failure;
        }
        catch (InvalidCastException)
        {
            result.Error = new ErrorInfo
            {
                Code = "core_audio_interface_unavailable",
                Stage = "IMMDevice.Activate",
            };
            WriteJson(result);
            return Failure;
        }
        catch (Exception)
        {
            // Keep the stdout schema stable and avoid leaking local paths or device
            // metadata through an unexpected exception message.
            result.Error = new ErrorInfo
            {
                Code = "unexpected_error",
                Stage = "doctor",
            };
            WriteJson(result);
            return Failure;
        }
        finally
        {
            if (mixFormat != IntPtr.Zero)
            {
                Marshal.FreeCoTaskMem(mixFormat);
            }

            ReleaseComObject(audioClientCom);
            ReleaseComObject(endpointCom);
            ReleaseComObject(enumeratorCom);
        }
    }

    private static void WriteJson(DoctorResult result)
    {
        Console.Out.WriteLine(JsonSerializer.Serialize(result, JsonOptions));
    }

    private static void EnsureSucceeded(int hResult, string stage)
    {
        if (hResult < 0)
        {
            throw new CaptureHelperException(new ErrorInfo
            {
                Code = "core_audio_call_failed",
                Stage = stage,
                HResult = FormatHResult(hResult),
            });
        }
    }

    private static void ReleaseComObject(object? value)
    {
        if (value is not null && Marshal.IsComObject(value))
        {
            Marshal.ReleaseComObject(value);
        }
    }

    private static string FormatHResult(int hResult) => $"0x{unchecked((uint)hResult):X8}";

    private static string DeviceStateName(uint state) => state switch
    {
        AudioDeviceState.Active => "active",
        AudioDeviceState.Disabled => "disabled",
        AudioDeviceState.NotPresent => "not_present",
        AudioDeviceState.Unplugged => "unplugged",
        _ => "unknown",
    };
}

internal sealed class CaptureHelperException : Exception
{
    public CaptureHelperException(ErrorInfo error)
    {
        Error = error;
    }

    public ErrorInfo Error { get; }
}

internal sealed class DoctorResult
{
    public int SchemaVersion { get; init; }

    public string Operation { get; init; } = string.Empty;

    public bool Ok { get; set; }

    public PlatformInfo Platform { get; init; } = new();

    public EndpointInfo? Endpoint { get; init; }

    public ErrorInfo? Error { get; set; }
}

internal sealed class PlatformInfo
{
    public bool Windows { get; init; }

    public string TargetFramework { get; init; } = "net8.0-windows";

    public string Architecture { get; init; } = string.Empty;

    public static PlatformInfo Current() => new()
    {
        Windows = OperatingSystem.IsWindows(),
        Architecture = RuntimeInformation.OSArchitecture.ToString(),
    };
}

internal sealed class EndpointInfo
{
    public string Flow { get; init; } = string.Empty;

    public string Role { get; init; } = string.Empty;

    public string? State { get; set; }

    public LoopbackInfo? Loopback { get; set; }

    public bool RecordingStarted { get; init; }
}

internal sealed class LoopbackInfo
{
    public bool Supported { get; init; }

    public bool Initialized { get; init; }

    public bool RecordingStarted { get; init; }

    public ErrorInfo? Error { get; set; }
}

internal sealed class ErrorInfo
{
    public string Code { get; init; } = string.Empty;

    public string Stage { get; init; } = string.Empty;

    public string? HResult { get; init; }
}

internal enum DataFlow
{
    Render = 0,
    Capture = 1,
    All = 2,
}

internal enum AudioRole
{
    Console = 0,
    Multimedia = 1,
    Communications = 2,
}

internal static class AudioDeviceState
{
    public const uint Active = 0x00000001;
    public const uint Disabled = 0x00000002;
    public const uint NotPresent = 0x00000004;
    public const uint Unplugged = 0x00000008;
}

internal static class ClsContext
{
    public const uint All = 0x17;
}

internal enum AudioClientShareMode
{
    Shared = 0,
    Exclusive = 1,
}

internal static class AudioClientStreamFlags
{
    public const uint Loopback = 0x00020000;
}

[ComImport]
[Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
internal sealed class MmDeviceEnumeratorComObject
{
}

[ComImport]
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IMMDeviceEnumerator
{
    [PreserveSig]
    int EnumAudioEndpoints(
        DataFlow dataFlow,
        uint stateMask,
        [MarshalAs(UnmanagedType.Interface)] out object devices);

    [PreserveSig]
    int GetDefaultAudioEndpoint(
        DataFlow dataFlow,
        AudioRole role,
        [MarshalAs(UnmanagedType.Interface)] out IMMDevice endpoint);

    [PreserveSig]
    int GetDevice(
        [MarshalAs(UnmanagedType.LPWStr)] string deviceId,
        [MarshalAs(UnmanagedType.Interface)] out IMMDevice endpoint);

    [PreserveSig]
    int RegisterEndpointNotificationCallback(
        [MarshalAs(UnmanagedType.Interface)] object client);

    [PreserveSig]
    int UnregisterEndpointNotificationCallback(
        [MarshalAs(UnmanagedType.Interface)] object client);
}

[ComImport]
[Guid("D666063F-1587-4E43-81F1-B948E807363F")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IMMDevice
{
    [PreserveSig]
    int Activate(
        ref Guid interfaceId,
        uint classContext,
        IntPtr activationParameters,
        [MarshalAs(UnmanagedType.IUnknown)] out object activatedInterface);

    [PreserveSig]
    int OpenPropertyStore(
        uint access,
        [MarshalAs(UnmanagedType.Interface)] out object propertyStore);

    [PreserveSig]
    int GetId(out IntPtr deviceId);

    [PreserveSig]
    int GetState(out uint state);
}

[ComImport]
[Guid("1CB9AD4C-DBFA-4C32-B178-C2F568A703B2")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IAudioClient
{
    [PreserveSig]
    int Initialize(
        AudioClientShareMode shareMode,
        uint streamFlags,
        long bufferDuration,
        long periodicity,
        IntPtr format,
        IntPtr audioSessionGuid);

    [PreserveSig]
    int GetBufferSize(out uint bufferSize);

    [PreserveSig]
    int GetStreamLatency(out long latency);

    [PreserveSig]
    int GetCurrentPadding(out uint padding);

    [PreserveSig]
    int IsFormatSupported(
        AudioClientShareMode shareMode,
        IntPtr format,
        out IntPtr closestMatch);

    [PreserveSig]
    int GetMixFormat(out IntPtr format);
}
