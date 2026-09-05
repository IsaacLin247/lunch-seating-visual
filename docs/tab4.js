// Tab 4, The Math: static explainer typeset with KaTeX (auto-render, loaded from the CDN).
export function createTab4() {
  const el = document.getElementById('tab-math');
  let rendered = false;
  function typeset() {
    if (rendered) return;
    if (typeof window.renderMathInElement !== 'function') return; // KaTeX still loading or offline
    window.renderMathInElement(el, {
      delimiters: [
        { left: '\\[', right: '\\]', display: true },
        { left: '\\(', right: '\\)', display: false },
      ],
      throwOnError: false,
    });
    rendered = true;
  }
  // KaTeX scripts are deferred; typeset once they are in, or on first view.
  if (document.readyState === 'complete') typeset();
  else window.addEventListener('load', typeset, { once: true });
  return {
    render() { typeset(); },
    resize() {},
  };
}
