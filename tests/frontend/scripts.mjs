// Loads the frontend's plain scripts into a bare JavaScript context -- no browser, no page -- so
// the logic in them can be tested on its own. The scripts share one global scope in the browser;
// here they share one vm context, in the order the page loads them.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const STATIC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'static');

// Just enough of a page for the scripts to load: they look up a few elements at the top level
// and register listeners; nothing here draws anything.
function element() {
  const node = {
    style: { setProperty() {} }, dataset: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    innerHTML: '', textContent: '', value: '', children: [],
    querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, setAttribute() {}, removeAttribute() {},
    appendChild() {}, append() {}, remove() {}, before() {},
  };
  return node;
}

// root: the path the page says the app is served under (<html data-root>), '' at the root.
export function loadScripts(names, extra = {}, { root = '' } = {}) {
  const documentElement = element();
  if (root) documentElement.dataset.root = root;
  const document = { querySelector: () => element(), querySelectorAll: () => [], createElement: () => element(), body: element(), documentElement, addEventListener() {} };
  const sandbox = {
    console, URL, URLSearchParams, Intl, Promise, Map, Set, Date, Math, JSON, setTimeout, clearTimeout, queueMicrotask, structuredClone,
    document, navigator: { onLine: true }, location: { href: 'http://ophirfigures.test/', origin: 'http://ophirfigures.test', pathname: '/', search: '', hash: '' },
    addEventListener() {}, removeEventListener() {}, scrollTo() {}, innerWidth: 1400,
    ...extra,
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  const context = vm.createContext(sandbox);
  for (const name of names) {
    const file = path.join(STATIC, name);
    vm.runInContext(readFileSync(file, 'utf8'), context, { filename: file });
  }
  // Objects made inside the context have that context's Array and Object, which assert's deep
  // comparison does not treat as equal to ours: plain data is copied over.
  const plain = value => (value && typeof value.then === 'function' ? value.then(plain)
    : value && typeof value === 'object' ? JSON.parse(JSON.stringify(value)) : value);
  // const/let at a script's top level are not properties of the global object: read them by name.
  return { context, run: expression => plain(vm.runInContext(expression, context)) };
}
