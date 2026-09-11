namespace ClaudeControlHelper;

// Pure policy: self-tests exercise the same decisions used by the UIA3 adapter.
internal static class ControlPolicy
{
    internal static bool VisiblePath(bool ancestorHidden, bool offscreen, bool enabled, bool hostVisible, bool hostBelongsToWindow) =>
        !ancestorHidden && !offscreen && enabled && hostVisible && hostBelongsToWindow;

    internal static string? TabLabel(string name)
    {
        var compact = string.Concat(name.Where(c => !char.IsWhiteSpace(c)));
        return compact switch
        {
            "Code" or "コード" or "Code、作業中" => "Code",
            "Chat" or "チャット" => "Chat",
            "Cowork" or "チャットとCowork" or "ChatandCowork" or "Chat&Cowork" => "Chat / Cowork",
            _ => null,
        };
    }

    internal static string? InputMethod(bool hasValue, bool valueReadOnly, bool hasLegacy, uint role, uint state, bool focusable)
    {
        if (!focusable) return null;
        if (hasValue) return valueReadOnly ? null : "value";
        // MSAA ROLE_SYSTEM_TEXT only; never a whole document or a protected editor.
        const uint forbidden = 0x1 | 0x40 | 0x8000 | 0x10000 | 0x20000000;
        return hasLegacy && role == 42 && (state & forbidden) == 0 && (state & 0x100000) != 0 ? "legacy_value" : null;
    }

    internal static bool WriteOnce(Func<string> read, Action<string> write, string expectedDigest, string text, bool allowReplace, Func<string, string> digest, Action dispatched)
    {
        var before = read();
        if (digest(before) != expectedDigest || (!allowReplace && before.Length != 0)) throw new InvalidOperationException("draft_changed");
        dispatched();
        // No fallback or retry after dispatch, even when readback or the provider fails.
        write(text);
        return read() == text;
    }

    internal static void SelfTest()
    {
        if (!VisiblePath(false, false, true, true, true) || VisiblePath(true, false, true, true, true) ||
            VisiblePath(false, true, true, true, true) || VisiblePath(false, false, false, true, true) ||
            VisiblePath(false, false, true, false, true) || VisiblePath(false, false, true, true, false)) throw new InvalidOperationException();
        if (TabLabel("チャットと Cowork") != "Chat / Cowork" || TabLabel("Code、作業中") != "Code" || TabLabel("Code project") != null) throw new InvalidOperationException();
        if (InputMethod(false, false, true, 42, 0x100000, true) != "legacy_value") throw new InvalidOperationException();
        foreach (uint forbidden in new uint[] { 1, 0x40, 0x8000, 0x10000, 0x20000000 })
            if (InputMethod(false, false, true, 42, 0x100000 | forbidden, true) != null) throw new InvalidOperationException();
        if (InputMethod(true, true, true, 42, 0x100000, true) != null || InputMethod(false, false, true, 15, 0x100000, true) != null || InputMethod(false, false, false, 42, 0x100000, true) != null || InputMethod(true, false, false, 0, 0, false) != null) throw new InvalidOperationException();
        string value = ""; int writes = 0, dispatches = 0;
        bool verified = WriteOnce(() => value, next => { writes++; value = next; }, "", "未送信", false, s => s, () => dispatches++);
        if (!verified || writes != 1 || dispatches != 1) throw new InvalidOperationException();
        try { WriteOnce(() => value, _ => writes++, "", "変更", true, s => s, () => dispatches++); throw new Exception(); } catch (InvalidOperationException) { }
        try { WriteOnce(() => value, _ => writes++, value, "変更", false, s => s, () => dispatches++); throw new Exception(); } catch (InvalidOperationException) { }
        if (writes != 1 || dispatches != 1) throw new InvalidOperationException();
        try { WriteOnce(() => "", _ => { writes++; throw new ArgumentException(); }, "", "未送信", false, s => s, () => dispatches++); throw new Exception(); } catch (ArgumentException) { }
        if (writes != 2 || dispatches != 2) throw new InvalidOperationException();
        if (WriteOnce(() => "", _ => writes++, "", "未送信", false, s => s, () => dispatches++) || writes != 3 || dispatches != 3) throw new InvalidOperationException();
        int reads = 0;
        try { WriteOnce(() => ++reads == 1 ? "" : throw new ArgumentException(), _ => writes++, "", "未送信", false, s => s, () => dispatches++); throw new Exception(); } catch (ArgumentException) { }
        if (reads != 2 || writes != 4 || dispatches != 4) throw new InvalidOperationException();
    }
}
