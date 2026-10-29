// What the page has besides the DOM: window.va from preload.js, and the libraries index.html loads as scripts.

interface Window {
  va: import('../va').Va;
  __screenshot?: (options: { select?: string; tab?: string }) => Promise<void>;
  vaPage: { loadCollections: () => Promise<void> };
}

declare const marked: typeof import('marked').marked;
declare const DOMPurify: typeof import('dompurify').default;
declare const Terminal: typeof import('@xterm/xterm').Terminal;
declare const FitAddon: typeof import('@xterm/addon-fit');
