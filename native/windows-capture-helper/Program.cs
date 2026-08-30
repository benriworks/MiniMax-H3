using System.Collections.Concurrent;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace WindowsCaptureHelper;

internal static class Program
{
    private const int Succeeded = 0;
    private const int Failure = 1;
    private const int InvalidArguments = 2;
    private const int MinimumDurationMs = 1_000;
    private const int MaximumDurationMs = 30_000;
    private const int SamplesPerSecond = 48_000;
    private const int Channels = 2;
    private const int BitsPerSample = 16;
    private const int BytesPerFrame = Channels * (BitsPerSample / 8);
    private const int MaximumPacketsPerDrain = 4_096;
    private const long MaximumPositionGapFrames = SamplesPerSecond / 2;
    private const long MaximumTrailingPaddingFrames = SamplesPerSecond / 4;
    private const long MaximumQpcDrift100ns = 250_000;
    private const long MaximumStartOffset100ns = 5_000_000;
    private const int MaximumInitialDiscontinuityCount = 1;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false,
    };

    [STAThread]
    public static int Main(string[] args)
    {
        ConfigureDpiAwareness();

        if (args.Length == 2 &&
            string.Equals(args[0], "doctor", StringComparison.OrdinalIgnoreCase) &&
            string.Equals(args[1], "--json", StringComparison.Ordinal))
        {
            return RunDoctor();
        }

        if (TryParseCaptureCommand(args, out var durationMs))
        {
            return RunLoopbackCapture(durationMs, waitForStartGate: true);
        }

        if (args.Length > 0 &&
            string.Equals(args[0], "capture-loopback", StringComparison.OrdinalIgnoreCase))
        {
            // Capture stdout is a binary-only channel. Invalid capture arguments
            // therefore report a fixed event on stderr and never write to stdout.
            WriteCaptureFailureSafely(
                null,
                new ErrorInfo
                {
                    Code = "invalid_arguments",
                    Stage = "command_line",
                });
            return InvalidArguments;
        }

        // Keep stdout machine-readable for unsupported non-capture commands. No
        // usage text, paths, device names, or diagnostics are emitted.
        WriteDoctorJson(new DoctorResult
        {
            SchemaVersion = 1,
            Operation = "doctor",
            Ok = false,
            CaptureAvailable = false,
            Platform = PlatformInfo.Current(),
            Error = new ErrorInfo
            {
                Code = "invalid_arguments",
                Stage = "command_line",
            },
        });
        return InvalidArguments;
    }

    private static bool TryParseCaptureCommand(string[] args, out int durationMs)
    {
        durationMs = 0;
        return args.Length == 4 &&
            string.Equals(args[0], "capture-loopback", StringComparison.OrdinalIgnoreCase) &&
            string.Equals(args[1], "--duration-ms", StringComparison.Ordinal) &&
            int.TryParse(
                args[2],
                NumberStyles.None,
                CultureInfo.InvariantCulture,
            out durationMs) &&
            durationMs >= MinimumDurationMs &&
            durationMs <= MaximumDurationMs &&
            string.Equals(args[3], "--start-gated", StringComparison.Ordinal);
    }

    private static int RunDoctor()
    {
        var result = new DoctorResult
        {
            SchemaVersion = 1,
            Operation = "doctor",
            Ok = false,
            CaptureAvailable = false,
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
        IntPtr fixedFormat = IntPtr.Zero;
        EventWaitHandle? audioReady = null;

        try
        {
            if (!OperatingSystem.IsWindows())
            {
                result.Error = new ErrorInfo
                {
                    Code = "windows_required",
                    Stage = "platform",
                };
                WriteDoctorJson(result);
                return Failure;
            }

            var display = PrimaryDisplayInfo();
            result.Display = display;

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

            fixedFormat = AllocateFixedCaptureFormat();
            audioReady = new EventWaitHandle(false, EventResetMode.AutoReset);
            var initializeHResult = audioClient.Initialize(
                AudioClientShareMode.Shared,
                AudioClientStreamFlags.CaptureLoopback,
                0,
                0,
                fixedFormat,
                IntPtr.Zero);

            var eventHandleHResult = Failure;
            if (initializeHResult >= 0)
            {
                eventHandleHResult = audioClient.SetEventHandle(
                    audioReady.SafeWaitHandle.DangerousGetHandle());
            }

            // Doctor proves the exact fixed-format capture stream can be
            // initialized, but deliberately never obtains IAudioCaptureClient,
            // calls Start, or reads a buffer.
            var loopbackReady = initializeHResult >= 0 && eventHandleHResult >= 0;
            result.Endpoint.Loopback = new LoopbackInfo
            {
                Supported = loopbackReady,
                Initialized = loopbackReady,
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
            else if (eventHandleHResult < 0)
            {
                result.Endpoint.Loopback.Error = new ErrorInfo
                {
                    Code = "loopback_event_handle_failed",
                    Stage = "IAudioClient.SetEventHandle",
                    HResult = FormatHResult(eventHandleHResult),
                };
            }

            var endpointActive = state == AudioDeviceState.Active;
            var displayReady = display.Width > 0 && display.Height > 0;
            result.CaptureAvailable = endpointActive && loopbackReady && displayReady;
            result.Ok = result.CaptureAvailable;

            if (!endpointActive)
            {
                result.Error = new ErrorInfo
                {
                    Code = "render_endpoint_not_active",
                    Stage = "IMMDevice.GetState",
                };
            }
            else if (!displayReady)
            {
                result.Error = new ErrorInfo
                {
                    Code = "primary_display_unavailable",
                    Stage = "GetSystemMetrics",
                };
            }
            else if (!loopbackReady)
            {
                result.Error = result.Endpoint.Loopback.Error;
            }

            WriteDoctorJson(result);
            return result.Ok ? Succeeded : Failure;
        }
        catch (CaptureHelperException exception)
        {
            result.Error = exception.Error;
            WriteDoctorJson(result);
            return Failure;
        }
        catch (COMException exception)
        {
            result.Error = new ErrorInfo
            {
                Code = "com_call_failed",
                Stage = "core_audio",
                HResult = FormatHResult(exception.HResult),
            };
            WriteDoctorJson(result);
            return Failure;
        }
        catch (InvalidCastException)
        {
            result.Error = new ErrorInfo
            {
                Code = "core_audio_interface_unavailable",
                Stage = "IMMDevice.Activate",
            };
            WriteDoctorJson(result);
            return Failure;
        }
        catch (Exception)
        {
            result.Error = new ErrorInfo
            {
                Code = "unexpected_error",
                Stage = "doctor",
            };
            WriteDoctorJson(result);
            return Failure;
        }
        finally
        {
            if (fixedFormat != IntPtr.Zero)
            {
                Marshal.FreeCoTaskMem(fixedFormat);
            }

            ReleaseComObject(audioClientCom);
            audioReady?.Dispose();
            ReleaseComObject(endpointCom);
            ReleaseComObject(enumeratorCom);
        }
    }

    private static int RunLoopbackCapture(int durationMs, bool waitForStartGate)
    {
        object? enumeratorCom = null;
        object? endpointCom = null;
        object? audioClientCom = null;
        object? captureClientCom = null;
        IntPtr fixedFormat = IntPtr.Zero;
        EventWaitHandle? audioReady = null;
        CaptureOutputSink? output = null;
        var counters = new CaptureCounters();
        var targetFrames = checked((long)durationMs * 48L);
        var targetBytes = checked(targetFrames * BytesPerFrame);
        var recordingStarted = false;
        var recordingStartedAtLeastOnce = false;
        ErrorInfo? failure = null;

        try
        {
            if (!OperatingSystem.IsWindows())
            {
                throw new CaptureHelperException(new ErrorInfo
                {
                    Code = "windows_required",
                    Stage = "platform",
                });
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
            if (state != AudioDeviceState.Active)
            {
                throw new CaptureHelperException(new ErrorInfo
                {
                    Code = "render_endpoint_not_active",
                    Stage = "IMMDevice.GetState",
                });
            }

            var audioClientIid = typeof(IAudioClient).GUID;
            var activateHResult = endpoint.Activate(
                ref audioClientIid,
                ClsContext.All,
                IntPtr.Zero,
                out var activatedClient);
            EnsureSucceeded(activateHResult, "IMMDevice.Activate");
            audioClientCom = activatedClient;
            var audioClient = (IAudioClient)activatedClient;

            fixedFormat = AllocateFixedCaptureFormat();
            audioReady = new EventWaitHandle(false, EventResetMode.AutoReset);
            EnsureSucceeded(
                audioClient.Initialize(
                    AudioClientShareMode.Shared,
                    AudioClientStreamFlags.CaptureLoopback,
                    0,
                    0,
                    fixedFormat,
                    IntPtr.Zero),
                "IAudioClient.Initialize");
            EnsureSucceeded(
                audioClient.SetEventHandle(audioReady.SafeWaitHandle.DangerousGetHandle()),
                "IAudioClient.SetEventHandle");

            var captureClientIid = typeof(IAudioCaptureClient).GUID;
            EnsureSucceeded(
                audioClient.GetService(ref captureClientIid, out var service),
                "IAudioClient.GetService");
            captureClientCom = service;
            var captureClient = (IAudioCaptureClient)service;

            // A dedicated writer keeps a blocked/downstream stdout pipe from
            // delaying the capture thread and therefore from delaying Stop.
            // The total queue is still bounded by the exact <= 5.76 MB result.
            output = new CaptureOutputSink(targetBytes);
            if (waitForStartGate)
            {
                WriteCaptureEvent(new CaptureEvent
                {
                    SchemaVersion = 1,
                    Operation = "capture_loopback",
                    EventName = "ready",
                    Ok = true,
                    DurationMs = durationMs,
                    Format = CaptureFormat.Fixed,
                    RecordingStarted = false,
                });
                ReadExactStartGate(Console.OpenStandardInput());
            }
            counters.StartQpc100ns = QpcNow100ns();
            EnsureSucceeded(audioClient.Start(), "IAudioClient.Start");
            recordingStarted = true;
            recordingStartedAtLeastOnce = true;
            counters.StartCallDuration100ns = checked(
                QpcNow100ns() - counters.StartQpc100ns);
            if (counters.StartCallDuration100ns < 0 ||
                counters.StartCallDuration100ns > MaximumStartOffset100ns)
            {
                throw new CaptureHelperException(new ErrorInfo
                {
                    Code = "capture_start_timestamp_invalid",
                    Stage = "QueryPerformanceCounter",
                });
            }
            WriteCaptureEvent(new CaptureEvent
            {
                SchemaVersion = 1,
                Operation = "capture_loopback",
                EventName = "started",
                Ok = true,
                DurationMs = durationMs,
                Format = CaptureFormat.Fixed,
                RecordingStarted = true,
            });

            var timer = Stopwatch.StartNew();
            while (timer.ElapsedMilliseconds < durationMs)
            {
                if (counters.FramesWritten < targetFrames)
                {
                    var remainingMs = durationMs - timer.Elapsed.TotalMilliseconds;
                    var waitMs = Math.Clamp((int)Math.Ceiling(remainingMs), 1, 100);
                    audioReady.WaitOne(waitMs);
                    DrainCapturePackets(captureClient, output, targetFrames, counters);
                }
                else
                {
                    var remainingMs = durationMs - timer.Elapsed.TotalMilliseconds;
                    if (remainingMs > 0)
                    {
                        Thread.Sleep(Math.Clamp((int)Math.Ceiling(remainingMs), 1, 25));
                    }
                }
            }

            if (counters.FramesWritten < targetFrames)
            {
                DrainCapturePackets(captureClient, output, targetFrames, counters);
            }
        }
        catch (CaptureHelperException exception)
        {
            failure = exception.Error;
        }
        catch (COMException exception)
        {
            failure = new ErrorInfo
            {
                Code = "com_call_failed",
                Stage = "core_audio",
                HResult = FormatHResult(exception.HResult),
            };
        }
        catch (InvalidCastException)
        {
            failure = new ErrorInfo
            {
                Code = "core_audio_interface_unavailable",
                Stage = "IAudioClient.GetService",
            };
        }
        catch (IOException)
        {
            failure = new ErrorInfo
            {
                Code = "capture_output_failed",
                Stage = "stdout",
            };
        }
        catch (OverflowException)
        {
            failure = new ErrorInfo
            {
                Code = "capture_size_invalid",
                Stage = "capture_buffer",
            };
        }
        catch (Exception)
        {
            failure = new ErrorInfo
            {
                Code = "unexpected_error",
                Stage = "capture_loopback",
            };
        }
        finally
        {
            if (recordingStarted && audioClientCom is IAudioClient audioClient)
            {
                try
                {
                    var stopHResult = audioClient.Stop();
                    if (stopHResult < 0 && failure is null)
                    {
                        failure = new ErrorInfo
                        {
                            Code = "capture_stop_failed",
                            Stage = "IAudioClient.Stop",
                            HResult = FormatHResult(stopHResult),
                        };
                    }
                }
                catch (COMException exception)
                {
                    failure ??= new ErrorInfo
                    {
                        Code = "capture_stop_failed",
                        Stage = "IAudioClient.Stop",
                        HResult = FormatHResult(exception.HResult),
                    };
                }
                catch (Exception)
                {
                    failure ??= new ErrorInfo
                    {
                        Code = "capture_stop_failed",
                        Stage = "IAudioClient.Stop",
                    };
                }
                recordingStarted = false;
            }

            // IAudioCaptureClient must be released on the same thread that
            // called GetService, and before its parent IAudioClient.
            ReleaseComObject(captureClientCom);
            ReleaseComObject(audioClientCom);
            audioReady?.Dispose();
            if (fixedFormat != IntPtr.Zero)
            {
                Marshal.FreeCoTaskMem(fixedFormat);
            }
            ReleaseComObject(endpointCom);
            ReleaseComObject(enumeratorCom);
            if (failure is not null)
            {
                output?.Abort();
            }
        }

        if (failure is not null)
        {
            WriteCaptureFailureSafely(
                durationMs,
                failure,
                recordingStartedAtLeastOnce);
            return Failure;
        }

        try
        {
            if (output is null)
            {
                throw new IOException();
            }

            if (!counters.HasPacket ||
                counters.TimestampErrorCount != 0 ||
                counters.DiscontinuityCount > MaximumInitialDiscontinuityCount ||
                counters.QpcSpan100ns <= 0)
            {
                throw new CaptureHelperException(new ErrorInfo
                {
                    Code = "capture_timing_unverified",
                    Stage = "IAudioCaptureClient.GetBuffer",
                });
            }

            var missingFrames = targetFrames - counters.FramesWritten;
            if (missingFrames < 0)
            {
                throw new OverflowException();
            }
            if (missingFrames > MaximumTrailingPaddingFrames)
            {
                throw new CaptureHelperException(new ErrorInfo
                {
                    Code = "capture_trailing_gap_exceeded",
                    Stage = "IAudioCaptureClient.GetBuffer",
                });
            }
            if (missingFrames > 0)
            {
                output.EnqueueZeroFrames(missingFrames);
                counters.FramesWritten += missingFrames;
                counters.PaddedFrames += missingFrames;
                counters.TailPaddedFrames += missingFrames;
            }
            output.CompleteAndWait(targetBytes);

            if (counters.FramesWritten != targetFrames)
            {
                throw new OverflowException();
            }

            WriteCaptureEvent(new CaptureEvent
            {
                SchemaVersion = 1,
                Operation = "capture_loopback",
                EventName = "completed",
                Ok = true,
                DurationMs = durationMs,
                Format = CaptureFormat.Fixed,
                // This field is an operation audit fact: Start succeeded at
                // least once. It does not mean the stream remains active;
                // Stop has already completed before this event is emitted.
                RecordingStarted = true,
                FramesWritten = counters.FramesWritten,
                BytesWritten = checked(counters.FramesWritten * BytesPerFrame),
                PaddedFrames = counters.PaddedFrames,
                SilentFrames = counters.SilentFrames,
                DiscontinuityCount = counters.DiscontinuityCount,
                TimestampErrorCount = counters.TimestampErrorCount,
                FirstPacketOffsetFrames = counters.FirstPacketOffsetFrames,
                GapFrames = counters.GapFrames,
                TailPaddedFrames = counters.TailPaddedFrames,
                FirstPacketQpcOffset100ns = counters.FirstPacketQpcOffset100ns,
                QpcSpan100ns = counters.QpcSpan100ns,
                MaxQpcDrift100ns = counters.MaxQpcDrift100ns,
                StartCallDuration100ns = counters.StartCallDuration100ns,
            });
            return Succeeded;
        }
        catch (CaptureHelperException exception)
        {
            WriteCaptureFailureSafely(
                durationMs,
                exception.Error,
                recordingStartedAtLeastOnce);
            return Failure;
        }
        catch (IOException)
        {
            WriteCaptureFailureSafely(
                durationMs,
                new ErrorInfo
                {
                    Code = "capture_output_failed",
                    Stage = "stdout",
                },
                recordingStartedAtLeastOnce);
            return Failure;
        }
        catch (OverflowException)
        {
            WriteCaptureFailureSafely(
                durationMs,
                new ErrorInfo
                {
                    Code = "capture_size_invalid",
                    Stage = "capture_buffer",
                },
                recordingStartedAtLeastOnce);
            return Failure;
        }
    }

    private static void DrainCapturePackets(
        IAudioCaptureClient captureClient,
        CaptureOutputSink output,
        long targetFrames,
        CaptureCounters counters)
    {
        for (var packetIndex = 0; packetIndex < MaximumPacketsPerDrain; packetIndex++)
        {
            EnsureSucceeded(
                captureClient.GetNextPacketSize(out var packetFrames),
                "IAudioCaptureClient.GetNextPacketSize");
            if (packetFrames == 0)
            {
                return;
            }

            var getBufferHResult = captureClient.GetBuffer(
                out var data,
                out var framesInPacket,
                out var flags,
                out var devicePosition,
                out var qpcPosition);
            EnsureSucceeded(getBufferHResult, "IAudioCaptureClient.GetBuffer");

            try
            {
                // Every successful GetBuffer call is paired with ReleaseBuffer
                // on this thread, including an empty-buffer success result.
                if (framesInPacket == 0)
                {
                    return;
                }

                if ((flags & AudioClientBufferFlags.DataDiscontinuity) != 0)
                {
                    counters.DiscontinuityCount++;
                    // WASAPI can mark the first packet after Start because the
                    // stream itself has just transitioned state. There is no
                    // previous packet to correlate in that case, so retain the
                    // audit counter and continue through the existing bounded
                    // start-offset, device-position, and QPC checks. A flag on
                    // any later packet remains a real mid-stream glitch and is
                    // rejected fail closed.
                    if (counters.HasPacket ||
                        counters.DiscontinuityCount > MaximumInitialDiscontinuityCount)
                    {
                        throw new CaptureHelperException(new ErrorInfo
                        {
                            Code = "capture_data_discontinuity",
                            Stage = "IAudioCaptureClient.GetBuffer",
                        });
                    }
                }
                if ((flags & AudioClientBufferFlags.TimestampError) != 0)
                {
                    counters.TimestampErrorCount++;
                    throw new CaptureHelperException(new ErrorInfo
                    {
                        Code = "capture_timestamp_error",
                        Stage = "IAudioCaptureClient.GetBuffer",
                    });
                }

                var packetQpc100ns = checked((long)qpcPosition);
                if (packetQpc100ns <= 0)
                {
                    throw new CaptureHelperException(new ErrorInfo
                    {
                        Code = "capture_timestamp_invalid",
                        Stage = "IAudioCaptureClient.GetBuffer",
                    });
                }

                long gapFrames;
                if (!counters.HasPacket)
                {
                    var startOffset100ns = checked(
                        packetQpc100ns - counters.StartQpc100ns);
                    if (startOffset100ns < 0)
                    {
                        throw new CaptureHelperException(new ErrorInfo
                        {
                            Code = "capture_start_timestamp_negative",
                            Stage = "IAudioCaptureClient.GetBuffer",
                        });
                    }
                    if (startOffset100ns > MaximumStartOffset100ns)
                    {
                        throw new CaptureHelperException(new ErrorInfo
                        {
                            Code = "capture_start_timestamp_offset_exceeded",
                            Stage = "IAudioCaptureClient.GetBuffer",
                        });
                    }
                    counters.HasPacket = true;
                    counters.FirstDevicePosition = devicePosition;
                    counters.ExpectedDevicePosition = devicePosition;
                    counters.FirstQpc100ns = packetQpc100ns;
                    counters.LastQpc100ns = packetQpc100ns;
                    // Some loopback drivers expose a non-zero absolute device
                    // position on the first packet, especially when that packet
                    // also carries the stream-transition discontinuity flag.
                    // Use that value only as the origin for later deltas. The
                    // bounded QPC interval after Start is the auditable source
                    // for initial zero padding on our newly created stream.
                    var postStartOffset100ns = Math.Max(
                        0,
                        checked(startOffset100ns - counters.StartCallDuration100ns));
                    counters.FirstPacketOffsetFrames = checked(
                        (postStartOffset100ns * SamplesPerSecond + 5_000_000L) /
                        10_000_000L);
                    if (counters.FirstPacketOffsetFrames > MaximumPositionGapFrames)
                    {
                        throw new CaptureHelperException(new ErrorInfo
                        {
                            Code = "capture_start_position_gap_exceeded",
                            Stage = "IAudioCaptureClient.GetBuffer",
                        });
                    }
                    counters.FirstPacketQpcOffset100ns = startOffset100ns;
                    var expectedStartOffset100ns = checked(
                        counters.StartCallDuration100ns +
                        counters.FirstPacketOffsetFrames * 10_000_000L /
                        SamplesPerSecond);
                    counters.MaxQpcDrift100ns = Math.Abs(checked(
                        startOffset100ns - expectedStartOffset100ns));
                    if (counters.MaxQpcDrift100ns > MaximumQpcDrift100ns)
                    {
                        throw new CaptureHelperException(new ErrorInfo
                        {
                            Code = "capture_timestamp_drift_exceeded",
                            Stage = "IAudioCaptureClient.GetBuffer",
                        });
                    }
                    gapFrames = counters.FirstPacketOffsetFrames;
                }
                else
                {
                    if (devicePosition < counters.ExpectedDevicePosition ||
                        packetQpc100ns <= counters.LastQpc100ns)
                    {
                        throw new CaptureHelperException(new ErrorInfo
                        {
                            Code = "capture_timestamp_non_monotonic",
                            Stage = "IAudioCaptureClient.GetBuffer",
                        });
                    }
                    gapFrames = checked((long)(
                        devicePosition - counters.ExpectedDevicePosition));
                    var deviceDeltaFrames = checked((long)(
                        devicePosition - counters.FirstDevicePosition));
                    var expectedQpcDelta100ns = checked(
                        deviceDeltaFrames * 10_000_000L / SamplesPerSecond);
                    var actualQpcDelta100ns = checked(
                        packetQpc100ns - counters.FirstQpc100ns);
                    var qpcDrift100ns = Math.Abs(checked(
                        actualQpcDelta100ns - expectedQpcDelta100ns));
                    counters.MaxQpcDrift100ns = Math.Max(
                        counters.MaxQpcDrift100ns, qpcDrift100ns);
                    if (qpcDrift100ns > MaximumQpcDrift100ns)
                    {
                        throw new CaptureHelperException(new ErrorInfo
                        {
                            Code = "capture_timestamp_drift_exceeded",
                            Stage = "IAudioCaptureClient.GetBuffer",
                        });
                    }
                    counters.LastQpc100ns = packetQpc100ns;
                    counters.QpcSpan100ns = checked(
                        packetQpc100ns - counters.FirstQpc100ns);
                }

                if (gapFrames < 0 ||
                    gapFrames > MaximumPositionGapFrames ||
                    counters.GapFrames + gapFrames > MaximumPositionGapFrames ||
                    counters.FramesWritten + gapFrames > targetFrames)
                {
                    throw new CaptureHelperException(new ErrorInfo
                    {
                        Code = "capture_position_gap_exceeded",
                        Stage = "IAudioCaptureClient.GetBuffer",
                    });
                }
                if (gapFrames > 0)
                {
                    output.EnqueueZeroFrames(gapFrames);
                    counters.FramesWritten += gapFrames;
                    counters.PaddedFrames += gapFrames;
                    counters.GapFrames += gapFrames;
                }

                var remainingFrames = Math.Max(0, targetFrames - counters.FramesWritten);
                var framesToWrite = (uint)Math.Min((long)framesInPacket, remainingFrames);
                if (framesToWrite == 0)
                {
                    continue;
                }

                if ((flags & AudioClientBufferFlags.Silent) != 0)
                {
                    output.EnqueueZeroFrames(framesToWrite);
                    counters.SilentFrames += framesToWrite;
                }
                else
                {
                    if (data == IntPtr.Zero)
                    {
                        throw new CaptureHelperException(new ErrorInfo
                        {
                            Code = "capture_packet_invalid",
                            Stage = "IAudioCaptureClient.GetBuffer",
                        });
                    }

                    var bytesToWrite = checked((int)(framesToWrite * BytesPerFrame));
                    var bytes = new byte[bytesToWrite];
                    Marshal.Copy(data, bytes, 0, bytesToWrite);
                    output.Enqueue(bytes);
                }
                counters.FramesWritten += framesToWrite;
                counters.ExpectedDevicePosition = checked(
                    devicePosition + framesInPacket);
            }
            finally
            {
                EnsureSucceeded(
                    captureClient.ReleaseBuffer(framesInPacket),
                    "IAudioCaptureClient.ReleaseBuffer");
            }
        }

        throw new CaptureHelperException(new ErrorInfo
        {
            Code = "capture_packet_limit_exceeded",
            Stage = "IAudioCaptureClient.GetNextPacketSize",
        });
    }

    private static IntPtr AllocateFixedCaptureFormat()
    {
        var format = new WaveFormatEx
        {
            FormatTag = WaveFormatTag.Pcm,
            Channels = Channels,
            SamplesPerSecond = SamplesPerSecond,
            AverageBytesPerSecond = SamplesPerSecond * BytesPerFrame,
            BlockAlign = BytesPerFrame,
            BitsPerSample = BitsPerSample,
            ExtraSize = 0,
        };
        var pointer = Marshal.AllocCoTaskMem(Marshal.SizeOf<WaveFormatEx>());
        Marshal.StructureToPtr(format, pointer, false);
        return pointer;
    }

    private static void ReadExactStartGate(Stream input)
    {
        var gate = new byte[2];
        var total = 0;
        using var timeout = new CancellationTokenSource(
            TimeSpan.FromSeconds(15));
        try
        {
            while (total < gate.Length)
            {
                var read = input.ReadAsync(
                    gate.AsMemory(total, gate.Length - total),
                    timeout.Token).AsTask().GetAwaiter().GetResult();
                if (read == 0)
                {
                    break;
                }
                total += read;
            }
        }
        catch (OperationCanceledException)
        {
            throw new CaptureHelperException(new ErrorInfo
            {
                Code = "start_gate_timeout",
                Stage = "start_gate",
            });
        }

        if (total != 1 || gate[0] != (byte)'S')
        {
            throw new CaptureHelperException(new ErrorInfo
            {
                Code = "start_gate_invalid",
                Stage = "start_gate",
            });
        }
    }

    private static long QpcNow100ns()
    {
        var ticks = Stopwatch.GetTimestamp();
        var frequency = Stopwatch.Frequency;
        return checked(
            (ticks / frequency) * 10_000_000L +
            (ticks % frequency) * 10_000_000L / frequency);
    }

    private static DisplayInfo PrimaryDisplayInfo()
    {
        return new DisplayInfo
        {
            Target = "primary_display",
            Width = NativeMethods.GetSystemMetrics(SystemMetric.PrimaryScreenWidth),
            Height = NativeMethods.GetSystemMetrics(SystemMetric.PrimaryScreenHeight),
        };
    }

    private static void ConfigureDpiAwareness()
    {
        if (!OperatingSystem.IsWindows())
        {
            return;
        }
        try
        {
            // A DPI-aware helper reports physical primary-display dimensions,
            // matching the fixed gdigrab video_size used by Studio.
            NativeMethods.SetProcessDpiAwarenessContext(new IntPtr(-4));
        }
        catch (EntryPointNotFoundException)
        {
            // Unsupported Windows builds are rejected by later capability checks.
        }
        catch (DllNotFoundException)
        {
            // Keep failure reporting on the stable doctor/capture contract.
        }
    }

    private static void WriteDoctorJson(DoctorResult result)
    {
        Console.Out.WriteLine(JsonSerializer.Serialize(result, JsonOptions));
    }

    private static void WriteCaptureEvent(CaptureEvent value)
    {
        Console.Error.WriteLine(JsonSerializer.Serialize(value, JsonOptions));
        Console.Error.Flush();
    }

    private static void WriteCaptureFailureSafely(
        int? durationMs,
        ErrorInfo error,
        bool recordingStarted = false)
    {
        try
        {
            WriteCaptureEvent(new CaptureEvent
            {
                SchemaVersion = 1,
                Operation = "capture_loopback",
                EventName = "failed",
                Ok = false,
                DurationMs = durationMs,
                Format = CaptureFormat.Fixed,
                RecordingStarted = recordingStarted,
                Error = error,
            });
        }
        catch (Exception)
        {
            // stderr is diagnostic-only. Never fall back to binary stdout.
        }
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
        try
        {
            if (value is not null && Marshal.IsComObject(value))
            {
                Marshal.ReleaseComObject(value);
            }
        }
        catch (InvalidComObjectException)
        {
            // Already released. Never replace the fixed operation result with
            // runtime-specific COM cleanup text.
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

internal sealed class CaptureCounters
{
    public long FramesWritten { get; set; }

    public long PaddedFrames { get; set; }

    public long SilentFrames { get; set; }

    public int DiscontinuityCount { get; set; }

    public int TimestampErrorCount { get; set; }

    public bool HasPacket { get; set; }

    public ulong FirstDevicePosition { get; set; }

    public ulong ExpectedDevicePosition { get; set; }

    public long StartQpc100ns { get; set; }

    public long FirstQpc100ns { get; set; }

    public long LastQpc100ns { get; set; }

    public long FirstPacketOffsetFrames { get; set; }

    public long GapFrames { get; set; }

    public long TailPaddedFrames { get; set; }

    public long FirstPacketQpcOffset100ns { get; set; }

    public long QpcSpan100ns { get; set; }

    public long MaxQpcDrift100ns { get; set; }

    public long StartCallDuration100ns { get; set; }
}

internal sealed class CaptureOutputSink
{
    private static readonly byte[] ZeroBlock = new byte[64 * 1024];
    private static readonly TimeSpan WriterCompletionTimeout = TimeSpan.FromSeconds(10);

    private readonly BlockingCollection<byte[]> _chunks = new();
    private readonly Stream _output;
    private readonly Task _writer;
    private readonly long _maximumBytes;
    private Exception? _failure;
    private long _submittedBytes;

    public CaptureOutputSink(long maximumBytes)
    {
        if (maximumBytes <= 0 || maximumBytes > 30_000L * 192L)
        {
            throw new OverflowException();
        }
        _maximumBytes = maximumBytes;
        _output = Console.OpenStandardOutput();
        _writer = Task.Run(WriteLoop);
    }

    public void Enqueue(byte[] bytes)
    {
        ArgumentNullException.ThrowIfNull(bytes);
        ThrowIfFailed();
        if (bytes.Length == 0)
        {
            return;
        }
        var nextTotal = checked(_submittedBytes + bytes.LongLength);
        if (nextTotal > _maximumBytes)
        {
            throw new OverflowException();
        }
        _chunks.Add(bytes);
        _submittedBytes = nextTotal;
        ThrowIfFailed();
    }

    public void EnqueueZeroFrames(long frames)
    {
        var bytesRemaining = checked(frames * 4L);
        while (bytesRemaining > 0)
        {
            var count = (int)Math.Min(bytesRemaining, ZeroBlock.Length);
            Enqueue(count == ZeroBlock.Length ? ZeroBlock : new byte[count]);
            bytesRemaining -= count;
        }
    }

    public void CompleteAndWait(long expectedBytes)
    {
        _chunks.CompleteAdding();
        if (!_writer.Wait(WriterCompletionTimeout))
        {
            throw new IOException();
        }
        ThrowIfFailed();
        if (_submittedBytes != expectedBytes)
        {
            throw new OverflowException();
        }
    }

    public void Abort()
    {
        try
        {
            _chunks.CompleteAdding();
        }
        catch (InvalidOperationException)
        {
            // Already complete.
        }
    }

    private void WriteLoop()
    {
        try
        {
            foreach (var bytes in _chunks.GetConsumingEnumerable())
            {
                _output.Write(bytes, 0, bytes.Length);
            }
            _output.Flush();
        }
        catch (Exception exception)
        {
            Interlocked.CompareExchange(ref _failure, exception, null);
        }
    }

    private void ThrowIfFailed()
    {
        if (Volatile.Read(ref _failure) is not null)
        {
            throw new IOException();
        }
    }
}

internal sealed class DoctorResult
{
    public int SchemaVersion { get; init; }

    public string Operation { get; init; } = string.Empty;

    public bool Ok { get; set; }

    public bool CaptureAvailable { get; set; }

    public PlatformInfo Platform { get; init; } = new();

    public DisplayInfo? Display { get; set; }

    public EndpointInfo? Endpoint { get; init; }

    public ErrorInfo? Error { get; set; }
}

internal sealed class CaptureEvent
{
    public int SchemaVersion { get; init; }

    public string Operation { get; init; } = string.Empty;

    [JsonPropertyName("event")]
    public string EventName { get; init; } = string.Empty;

    public bool Ok { get; init; }

    public int? DurationMs { get; init; }

    public CaptureFormat Format { get; init; } = CaptureFormat.Fixed;

    public bool RecordingStarted { get; init; }

    public long? FramesWritten { get; init; }

    public long? BytesWritten { get; init; }

    public long? PaddedFrames { get; init; }

    public long? SilentFrames { get; init; }

    public int? DiscontinuityCount { get; init; }

    public int? TimestampErrorCount { get; init; }

    public long? FirstPacketOffsetFrames { get; init; }

    public long? GapFrames { get; init; }

    public long? TailPaddedFrames { get; init; }

    public long? FirstPacketQpcOffset100ns { get; init; }

    public long? QpcSpan100ns { get; init; }

    public long? MaxQpcDrift100ns { get; init; }

    public long? StartCallDuration100ns { get; init; }

    public ErrorInfo? Error { get; init; }
}

internal sealed class CaptureFormat
{
    public static CaptureFormat Fixed => new()
    {
        Encoding = "s16le",
        SamplesPerSecond = 48_000,
        Channels = 2,
        BitsPerSample = 16,
        BytesPerFrame = 4,
    };

    public string Encoding { get; init; } = string.Empty;

    public int SamplesPerSecond { get; init; }

    public int Channels { get; init; }

    public int BitsPerSample { get; init; }

    public int BytesPerFrame { get; init; }
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

internal sealed class DisplayInfo
{
    public string Target { get; init; } = string.Empty;

    public int Width { get; init; }

    public int Height { get; init; }
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

[StructLayout(LayoutKind.Sequential, Pack = 2)]
internal struct WaveFormatEx
{
    public ushort FormatTag;
    public ushort Channels;
    public uint SamplesPerSecond;
    public uint AverageBytesPerSecond;
    public ushort BlockAlign;
    public ushort BitsPerSample;
    public ushort ExtraSize;
}

internal static class WaveFormatTag
{
    public const ushort Pcm = 0x0001;
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
    public const uint EventCallback = 0x00040000;
    public const uint SrcDefaultQuality = 0x08000000;
    public const uint AutoConvertPcm = 0x80000000;
    public const uint CaptureLoopback =
        Loopback | EventCallback | SrcDefaultQuality | AutoConvertPcm;
}

internal static class AudioClientBufferFlags
{
    public const uint DataDiscontinuity = 0x00000001;
    public const uint Silent = 0x00000002;
    public const uint TimestampError = 0x00000004;
}

internal static class SystemMetric
{
    public const int PrimaryScreenWidth = 0;
    public const int PrimaryScreenHeight = 1;
}

internal static class NativeMethods
{
    [DllImport("user32.dll")]
    public static extern int GetSystemMetrics(int index);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetProcessDpiAwarenessContext(IntPtr value);
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

    [PreserveSig]
    int GetDevicePeriod(out long defaultPeriod, out long minimumPeriod);

    [PreserveSig]
    int Start();

    [PreserveSig]
    int Stop();

    [PreserveSig]
    int Reset();

    [PreserveSig]
    int SetEventHandle(IntPtr eventHandle);

    [PreserveSig]
    int GetService(
        ref Guid interfaceId,
        [MarshalAs(UnmanagedType.IUnknown)] out object service);
}

[ComImport]
[Guid("C8ADBD64-E71E-48A0-A4DE-185C395CD317")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IAudioCaptureClient
{
    [PreserveSig]
    int GetBuffer(
        out IntPtr data,
        out uint framesToRead,
        out uint flags,
        out ulong devicePosition,
        out ulong qpcPosition);

    [PreserveSig]
    int ReleaseBuffer(uint framesRead);

    [PreserveSig]
    int GetNextPacketSize(out uint packetFrames);
}
