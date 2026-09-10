import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { cancelRender, continueRender, delayRender, staticFile } from 'remotion';

export const SCREEN_FONT_FAMILY = 'Studio Noto Sans JP';
export const SCREEN_FONT_ASSET = 'template-assets/NotoSansJP-Variable.ttf';
const loads = new Map<string, Promise<void>>();

/** Load the pinned OFL font locally; never capture a silent system fallback. */
export const loadScreenTypography = (): Promise<void> => {
  const url = staticFile(SCREEN_FONT_ASSET);
  const existing = loads.get(url);
  if (existing) return existing;
  const font = new FontFace(SCREEN_FONT_FAMILY, `url("${url}")`, {
    style: 'normal', weight: '100 900', display: 'block',
  });
  const loading = font.load().then((loaded) => {
    document.fonts.add(loaded);
    if (!document.fonts.check(`700 76px "${SCREEN_FONT_FAMILY}"`, '日本語の見出し')) {
      throw new Error('The bundled Japanese headline font could not be verified');
    }
  });
  loads.set(url, loading);
  // A failed preview can retry when the source becomes available again.
  void loading.catch(() => { if (loads.get(url) === loading) loads.delete(url); });
  return loading;
};

export const ScreenTypography = ({ children }: { children: ReactNode }) => {
  const [ready, setReady] = useState(false);
  const [handle] = useState(() => delayRender('Bundled Japanese headline font', { timeoutInMilliseconds: 30_000 }));
  useEffect(() => {
    let disposed = false;
    void loadScreenTypography().then(() => {
      if (!disposed) setReady(true);
      continueRender(handle);
    }).catch((error: unknown) => {
      if (disposed) continueRender(handle);
      else cancelRender(error instanceof Error ? error : new Error('Japanese headline font load failed'));
    });
    return () => { disposed = true; };
  }, [handle]);
  return ready ? children : null;
};
