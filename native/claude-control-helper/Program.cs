using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Definitions;
using FlaUI.UIA3;

namespace ClaudeControlHelper;

internal static class Program
{
    internal const string AppId = "Claude_pzs8sxrjxfjjc!Claude";
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower, UnmappedMemberHandling = System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow };
    private static bool dispatched;
    internal record Identity(long Hwnd, int Pid, long ProcessStarted, string ProcessPath, string WindowClass, string PackageFamily, string PackageFullName, string ApplicationId, string PackageRoot, int Width, int Height);
    internal record Request(string Operation, Identity? Window, string? Fingerprint, string? Target, string? Text, bool AllowReplace);
    internal record Control(string Id, string Kind, string Label, int[] RuntimeId, int Characters, string ValueDigest, bool? Selected, double X, double Y, double Width, double Height, string Method, long NativeHost);
    private record Diagnostics(string Engine, string View, int InspectedNodes, int Documents, int HiddenNodes, int UnsupportedEditors, int SupportedInputs, int SupportedTabs);
    private record Snapshot(string Fingerprint, List<Control> Controls, Diagnostics Diagnostics);
    private sealed record Bound(Control Info, Func<string>? Read, Action<string>? Write, Action? Select, Func<bool>? IsSelected, Action Verify);
    private static string Hash(string text) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text)));
    private static bool ValidText(string? text) => text is { Length: > 0 and <= 4000 } && !text.Any(c => char.IsControl(c) && c != '\n') && !text.Contains('\u2028') && !text.Contains('\u2029');
    private static string? TabLabel(string name) => ControlPolicy.TabLabel(name);

    [STAThread]
    public static int Main(string[] args)
    {
        if (args.SequenceEqual(new[] { "self-test" })) return SelfTest();
        if (args.Length != 0) return 2;
        try
        {
            Console.InputEncoding = new UTF8Encoding(false, true);
            Console.OutputEncoding = new UTF8Encoding(false);
            var buffer = new char[32769]; int used = 0, read;
            while (used < buffer.Length && (read = Console.In.Read(buffer, used, buffer.Length - used)) > 0) used += read;
            if (used > 32768) throw new InvalidOperationException();
            var request = JsonSerializer.Deserialize<Request>(new string(buffer, 0, used), Json) ?? throw new InvalidOperationException();
            Validate(request);
            if (request.Operation == "launch")
            {
                // Fixed MSIX activation. No shell, arguments, deep links or installation.
                var type = Type.GetTypeFromCLSID(new Guid("45BA127D-10A8-46EA-8AB7-56EA9078943C"), true)!;
                var manager = (IApplicationActivationManager)Activator.CreateInstance(type)!;
                try { dispatched = true; Marshal.ThrowExceptionForHR(manager.ActivateApplication(AppId, null, 0, out _)); }
                finally { Marshal.FinalReleaseComObject(manager); }
                Write(new { ok = true, protocol_version = 2, effect_verified = false, code = "activation_requested" });
                return 0;
            }
            var identity = request.Window!;
            VerifyWindow(identity);
            using var automation = new UIA3Automation { ConnectionTimeout = TimeSpan.FromSeconds(2), TransactionTimeout = TimeSpan.FromSeconds(2) };
            var (snapshot, bound) = Inspect(identity, automation);
            if (request.Operation == "inspect")
            {
                // A single bounded second observation accommodates lazy Chromium exposure.
                // This retries reading only, never an action and never a provider exception.
                if (snapshot.Controls.Count == 0)
                {
                    Thread.Sleep(300);
                    (snapshot, bound) = Inspect(identity, automation);
                }
                Write(new { ok = true, protocol_version = 2, snapshot.Fingerprint, snapshot.Controls, snapshot.Diagnostics }); return 0;
            }
            if (snapshot.Fingerprint != request.Fingerprint) throw new InvalidOperationException("state_changed");
            var target = bound.Single(item => item.Info.Id == request.Target);
            VerifyWindow(identity);
            target.Verify();
            bool verified;
            if (request.Operation == "input")
            {
                if (target.Read == null || target.Write == null || target.Info.Kind != "input") throw new InvalidOperationException();
                verified = ControlPolicy.WriteOnce(target.Read, next => { target.Verify(); target.Write(next); }, target.Info.ValueDigest, request.Text!, request.AllowReplace, Hash, () => dispatched = true);
            }
            else
            {
                if (target.Info.Kind != "tab" || target.Select == null) throw new InvalidOperationException();
                dispatched = true;
                target.Select();
                verified = target.IsSelected?.Invoke() == true;
            }
            VerifyWindow(identity);
            Write(new { ok = true, protocol_version = 2, effect_verified = verified, code = verified ? "effect_verified" : "dispatched_review_required" });
            return 0;
        }
        catch
        {
            // Never echo UI text, request text, exception details or local paths.
            Write(new { ok = false, protocol_version = 2, dispatched, code = dispatched ? "outcome_unknown" : "unsupported_or_changed" });
            return 1;
        }
    }

    private static void Validate(Request r)
    {
        if (r.Operation == "launch")
        {
            if (r.Window != null || r.Fingerprint != null || r.Target != null || r.Text != null || r.AllowReplace) throw new InvalidOperationException();
            return;
        }
        if (r.Window == null || r.Window.ApplicationId != AppId || r.Window.WindowClass != "Chrome_WidgetWin_1") throw new InvalidOperationException();
        if (r.Operation == "inspect")
        {
            if (r.Fingerprint != null || r.Target != null || r.Text != null || r.AllowReplace) throw new InvalidOperationException();
            return;
        }
        if (r.Operation is not ("tab" or "input") || r.Fingerprint is not { Length: 64 } || r.Target is not { Length: 64 }) throw new InvalidOperationException();
        if (r.Operation == "input" ? !ValidText(r.Text) : r.Text != null || r.AllowReplace) throw new InvalidOperationException();
    }

    private static (Snapshot, List<Bound>) Inspect(Identity identity, UIA3Automation automation)
    {
        var root = automation.FromHandle((IntPtr)identity.Hwnd);
        var rectangle = root.Properties.BoundingRectangle.Value;
        var found = new List<Bound>();
        var stack = new Stack<(AutomationElement Node, bool Hidden, bool Mode, long Host)>();
        stack.Push((root, false, false, identity.Hwnd));
        var walker = automation.TreeWalkerFactory.GetRawViewWalker();
        int count = 0, documents = 0, hiddenNodes = 0, unsupportedEditors = 0;
        while (stack.TryPop(out var frame))
        {
            if (++count > 2500) throw new InvalidOperationException("tree_too_large");
            var element = frame.Node;
            var current = element.Properties;
            if (current.IsPassword.Value) continue;
            var type = current.ControlType.Value;
            if (type == ControlType.Document) documents++;
            var host = current.NativeWindowHandle.Value.ToInt64();
            if (host == 0) host = frame.Host;
            bool hidden = !ControlPolicy.VisiblePath(frame.Hidden, current.IsOffscreen.Value, current.IsEnabled.Value,
                IsWindowVisible((IntPtr)host), GetAncestor((IntPtr)host, 2) == (IntPtr)identity.Hwnd);
            if (hidden) hiddenNodes++;
            var rect = current.BoundingRectangle.Value;
            bool mode = frame.Mode || ((type == ControlType.Group || type == ControlType.Tab) && current.Name.Value is "モード" or "Mode");
            if (!hidden && rect.Width > 0 && rect.Height > 0 && rectangle.Contains(rect))
            {
                var runtime = current.RuntimeId.Value;
                string? label = null, method = null;
                Func<string>? read = null; Action<string>? write = null;
                Action? select = null; Func<bool>? selected = null;
                if (mode && (type == ControlType.TabItem || type == ControlType.Button) && rect.Y <= rectangle.Y + 160)
                {
                    label = TabLabel(current.Name.Value);
                    var selection = element.Patterns.SelectionItem.PatternOrDefault;
                    var invoke = element.Patterns.Invoke.PatternOrDefault;
                    if (selection != null) { select = selection.Select; selected = () => selection.IsSelected.Value; method = "selection"; }
                    else if (invoke != null) { select = invoke.Invoke; method = "invoke"; }
                    else label = null;
                }
                else if (type == ControlType.Edit || type == ControlType.Document)
                {
                    var value = element.Patterns.Value.PatternOrDefault;
                    var legacy = value == null ? element.Patterns.LegacyIAccessible.PatternOrDefault : null;
                    method = ControlPolicy.InputMethod(value != null, value?.IsReadOnly.Value ?? false, legacy != null,
                        legacy != null ? (uint)legacy.Role.Value : 0, legacy != null ? (uint)legacy.State.Value : 0, current.IsKeyboardFocusable.Value);
                    if (method == "value") { read = () => value!.Value.Value; write = next => { if (value!.IsReadOnly.Value) throw new InvalidOperationException(); value.SetValue(next); }; }
                    else if (method == "legacy_value") { read = () => legacy!.Value.Value; write = next => {
                        if (ControlPolicy.InputMethod(false, false, true, (uint)legacy!.Role.Value, (uint)legacy.State.Value, element.Properties.IsKeyboardFocusable.Value) != "legacy_value") throw new InvalidOperationException();
                        legacy.SetValue(next);
                    }; }
                    else if (type == ControlType.Edit || current.IsKeyboardFocusable.Value) unsupportedEditors++;
                }
                if (label != null || read != null)
                {
                    var content = read?.Invoke() ?? "";
                    if (content.Length > 16000) throw new InvalidOperationException("value_too_large");
                    string kind = read == null ? "tab" : "input";
                    string id = Hash(kind + ":" + string.Join(',', runtime));
                    var info = new Control(id, kind, label ?? $"入力欄 {found.Count(item => item.Info.Kind == "input") + 1}", runtime,
                        content.Length, Hash(content), selected?.Invoke(), rect.X - rectangle.X, rect.Y - rectangle.Y, rect.Width, rect.Height, method!, host);
                    found.Add(new Bound(info, read, write, select, selected, () => VerifyTarget(identity, element, automation)));
                    if (found.Count > 24) throw new InvalidOperationException("too_many_controls");
                }
            }
            // Include raw intermediate containers, but never promote hidden descendants.
            int siblings = 0;
            for (var child = walker.GetFirstChild(element); child != null; child = walker.GetNextSibling(child))
            {
                if (++siblings + count > 2500) throw new InvalidOperationException("tree_too_large");
                stack.Push((child, hidden, mode, host));
            }
        }
        VerifyWindow(identity);
        var controls = found.Select(item => item.Info).OrderBy(item => item.Id, StringComparer.Ordinal).ToList();
        var diagnostics = new Diagnostics("uia3", "raw", count, documents, hiddenNodes, unsupportedEditors, controls.Count(item => item.Kind == "input"), controls.Count(item => item.Kind == "tab"));
        return (new Snapshot(Hash(JsonSerializer.Serialize(new { identity, controls }, Json)), controls, diagnostics), found);
    }

    private static void VerifyTarget(Identity identity, AutomationElement target, UIA3Automation automation)
    {
        // Recheck the entire live ancestry immediately before mutation: a hidden Chat
        // renderer must not receive input when Code is visible, even if its tree survives.
        var walker = automation.TreeWalkerFactory.GetRawViewWalker();
        var rootRectangle = automation.FromHandle((IntPtr)identity.Hwnd).Properties.BoundingRectangle.Value;
        var targetRectangle = target.Properties.BoundingRectangle.Value;
        if (targetRectangle.Width <= 0 || targetRectangle.Height <= 0 || !rootRectangle.Contains(targetRectangle)) throw new InvalidOperationException();
        var node = target;
        for (int depth = 0; node != null && depth < 100; depth++, node = walker.GetParent(node))
        {
            var p = node.Properties;
            if (p.IsOffscreen.Value || !p.IsEnabled.Value || p.IsPassword.Value) throw new InvalidOperationException();
            var host = p.NativeWindowHandle.Value;
            if (host != IntPtr.Zero && (!IsWindowVisible(host) || GetAncestor(host, 2) != (IntPtr)identity.Hwnd)) throw new InvalidOperationException();
            if (host == (IntPtr)identity.Hwnd && p.ControlType.Value == ControlType.Window) return;
        }
        throw new InvalidOperationException();
    }

    private static void VerifyWindow(Identity expected)
    {
        var hwnd = (IntPtr)expected.Hwnd;
        if (!IsWindowVisible(hwnd) || IsIconic(hwnd) || GetAncestor(hwnd, 2) != hwnd) throw new InvalidOperationException();
        GetWindowThreadProcessId(hwnd, out uint pid);
        if (pid != expected.Pid || expected.PackageFamily != "Claude_pzs8sxrjxfjjc") throw new InvalidOperationException();
        using var process = Process.GetProcessById((int)pid);
        if (process.StartTime.ToUniversalTime().ToFileTimeUtc() != expected.ProcessStarted) throw new InvalidOperationException();
        var path = new StringBuilder(32768); uint size = 32768;
        if (!QueryFullProcessImageName(process.Handle, 0, path, ref size) || !string.Equals(Path.GetFullPath(path.ToString()), expected.ProcessPath, StringComparison.OrdinalIgnoreCase) || !string.Equals(Path.GetFileName(path.ToString()), "claude.exe", StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException();
        if (PackageText(GetPackageFamilyName, process.Handle) != expected.PackageFamily || PackageText(GetPackageFullName, process.Handle) != expected.PackageFullName || PackageText(GetApplicationUserModelId, process.Handle) != AppId) throw new InvalidOperationException();
        var className = new StringBuilder(256);
        if (GetClassName(hwnd, className, 256) == 0 || className.ToString() != expected.WindowClass || !GetClientRect(hwnd, out var rect) || rect.Right - rect.Left != expected.Width || rect.Bottom - rect.Top != expected.Height) throw new InvalidOperationException();
    }
    private delegate int PackageCall(IntPtr process, ref uint size, StringBuilder? text);
    private static string PackageText(PackageCall call, IntPtr handle)
    {
        uint size = 0;
        if (call(handle, ref size, null) != 122 || size > 32768 || size == 0) throw new InvalidOperationException();
        var text = new StringBuilder((int)size);
        if (call(handle, ref size, text) != 0) throw new InvalidOperationException();
        return text.ToString();
    }
    private static void Write(object result) => Console.WriteLine(JsonSerializer.Serialize(result, Json));
    private static int SelfTest()
    {
        ControlPolicy.SelfTest();
        if (!ValidText("撮影用\n未送信の例") || ValidText("\u001b[31m") || ValidText("hello\r\n") || ValidText(new string('a', 4001)) || TabLabel("Delete") != null || TabLabel("Code") != "Code") return 1;
        Validate(new Request("launch", null, null, null, null, false));
        foreach (var operation in new[] { "send", "enter", "shell", "terminal", "click", "launch-other" })
        {
            try { Validate(new Request(operation, null, null, null, null, false)); return 1; } catch (InvalidOperationException) { }
        }
        Write(new { ok = true, protocol_version = 2, native_actions_performed = false }); return 0;
    }
    [StructLayout(LayoutKind.Sequential)] private struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern IntPtr GetAncestor(IntPtr hwnd, uint flags);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(IntPtr hwnd, StringBuilder text, int length);
    [DllImport("user32.dll")] private static extern bool GetClientRect(IntPtr hwnd, out Rect rect);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, EntryPoint = "QueryFullProcessImageNameW")] private static extern bool QueryFullProcessImageName(IntPtr process, int flags, StringBuilder path, ref uint size);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern int GetPackageFamilyName(IntPtr process, ref uint size, StringBuilder? text);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern int GetPackageFullName(IntPtr process, ref uint size, StringBuilder? text);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern int GetApplicationUserModelId(IntPtr process, ref uint size, StringBuilder? text);
    [ComImport, Guid("2e941141-7f97-4756-ba1d-9decde894a3d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IApplicationActivationManager
    {
        [PreserveSig] int ActivateApplication([MarshalAs(UnmanagedType.LPWStr)] string appId, [MarshalAs(UnmanagedType.LPWStr)] string? arguments, int options, out uint pid);
        [PreserveSig] int ActivateForFile(IntPtr appId, IntPtr items, IntPtr verb, out uint pid);
        [PreserveSig] int ActivateForProtocol(IntPtr appId, IntPtr items, out uint pid);
    }
}
