export type AnimationFrameRequester = (callback: FrameRequestCallback) => number;

/**
 * Resolve only after a state update has had a render frame and a following
 * paint opportunity. Callers may inject a frame scheduler for runtime tests.
 */
export function waitForBrowserPaint(
  requestFrame: AnimationFrameRequester = window.requestAnimationFrame.bind(window),
): Promise<void> {
  return new Promise((resolve) => {
    requestFrame(() => requestFrame(() => resolve()));
  });
}
