// The logic in static/js that needs no browser: formatting, escaping, filters, grouping, the
// bookmarklet.
import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import vm from 'node:vm';
import { loadScripts } from './scripts.mjs';

const { run } = loadScripts(['js/core.js', 'js/figures-ui.js', 'js/views.js', 'js/dashboard.js']);
const set = (expression, value) => run(`${expression}=${JSON.stringify(value)}`);

set('state.boot', {
  user: { id: 7, display_name: 'Alex Morgan' }, settings: {},
  conditions: { sealed: 'Neu, versiegelt', boxed: 'Geöffnet, mit Karton' },
  statuses: { ordered: 'Bestellt', paid: 'Bezahlt', shipped: 'Versendet', delivered: 'Angekommen', cancelled: 'Storniert' },
  watchlists: [{ id: 3, name: 'Wunschliste', is_default: 1, count: 0 }, { id: 4, name: 'Grails', is_default: 0, count: 2 }],
});

describe('text and money', () => {
  test('escapeHtml neutralises markup', () => {
    assert.equal(run(`escapeHtml('<img src=x onerror="a&b">')`), '&lt;img src=x onerror=&quot;a&amp;b&quot;&gt;');
    assert.equal(run(`escapeHtml(null)`), '');
    assert.equal(run(`escapeHtml(0)`), '0');
  });

  test('amounts in euros and yen', () => {
    assert.match(run(`money(189.9)`), /^189,90\s€$/);
    assert.match(run(`currencyMoney(22000,'JPY')`), /^22\.000\s¥$/);
    assert.equal(run(`moneyOrDash(null)`), '–');
    assert.match(run(`currencyMoney(5,'XYZ')`), /5/, 'an unknown currency still shows the amount');
  });

  test('dates as precise as they are known', () => {
    assert.equal(run(`partialDate('2026')`), '2026');
    assert.equal(run(`partialDate('2026-03')`), 'März 2026');
    assert.equal(run(`partialDate('2026-03-14')`), '14.03.2026');
    assert.equal(run(`partialDate('')`), '');
  });

  test('plural', () => {
    assert.equal(run(`plural(1,'Figur','Figuren')`), '1 Figur');
    assert.equal(run(`plural(3,'Figur','Figuren')`), '3 Figuren');
  });
});

describe('search boxes', () => {
  const matches = (query, fields) => run(`searchMatcher(${JSON.stringify(query)})(${JSON.stringify(fields)})`);

  test('every word somewhere, a letter off allowed', () => {
    const miku = ['Hatsune Miku: Racing 2024 Ver.', 'Good Smile Company', 'Vocaloid'];
    assert.equal(matches('miku good smile', miku), true);
    assert.equal(matches('hatsunemiku', miku), true);
    assert.equal(matches('Hatsume', miku), true);
    assert.equal(matches('miku kotobukiya', miku), false);
  });

  test('regular expressions where their syntax is used', () => {
    assert.equal(matches('Rem|Ram', ['figma Ram']), true);
    assert.equal(matches('^figma', ['Nendoroid figma']), false);
    assert.equal(matches('(Twins', ['Rem & Ram: Twins Ver.']), true, 'no valid expression: taken literally');
  });
});

describe('figure views', () => {
  test('a tile escapes the name and shows what the account has', () => {
    const html = run(`figureTile({id:5,name:'<b>Rem</b>',manufacturer:'Kadokawa',release_date:'2026-12',owned:2,preordered:1,wished:true,market_value:230,image_version:'abc'})`);
    assert.ok(html.includes('&lt;b&gt;Rem&lt;/b&gt;') && !html.includes('<b>Rem</b>'));
    assert.ok(html.includes('×2') && html.includes('VB') && html.includes('fig-heart active') && html.includes('Dezember 2026'));
    assert.ok(html.includes('/images/figures/5/thumb?v=abc'));
  });

  test('filters go to the server without the empty ones', () => {
    assert.equal(run(`filterQuery({q:'',mode:'all',category:'Nendoroid',year:'',sort:'release',direction:''})`), 'mode=all&category=Nendoroid&sort=release');
  });

  test('preorders are grouped: overdue first, then by month, without a date, then closed ones', () => {
    const month = new Date().toISOString().slice(0, 7);
    const next = new Date(new Date().setMonth(new Date().getMonth() + 2)).toISOString().slice(0, 7);
    const rows = [
      { id: 1, status: 'ordered', expected_release: next }, { id: 2, status: 'paid', expected_release: '2020-01' },
      { id: 3, status: 'shipped', expected_release: '' }, { id: 4, status: 'delivered', expected_release: '2024-01' },
      { id: 5, status: 'ordered', expected_release: `${month}-20` },
    ];
    const groups = run(`preorderGroups(${JSON.stringify(rows)})`).map(group => [group.label.split(' ·')[0], group.rows.map(row => row.id)]);
    assert.deepEqual(groups.map(([, ids]) => ids), [[2], [5], [1], [3], [4]]);
    assert.equal(groups[0][0], 'Überfällig');
    assert.equal(groups[1][0], 'Diesen Monat');
    assert.equal(groups[3][0], 'Ohne Termin');
    assert.equal(groups[4][0], 'Angekommen');
  });

  test('the default list', () => {
    assert.equal(run(`defaultListId()`), 3);
  });
});

describe('the bookmarklet', () => {
  const href = run(`bookmarkletHref()`);
  const code = decodeURIComponent(href.slice('javascript:'.length));

  test('is a javascript: link with valid code for this app', () => {
    assert.ok(href.startsWith('javascript:'));
    assert.doesNotThrow(() => new vm.Script(code));
    assert.ok(code.includes("'http://ophirfigures.test/#import='"));
  });

  test('reads a page and opens the app with what it found', () => {
    // A product page as the bookmarklet sees it, reduced to what it asks the DOM for.
    const el = (props = {}) => ({ innerText: '', getAttribute: name => props.attrs?.[name] ?? null, querySelector: () => null, querySelectorAll: () => [], ...props });
    const label = text => el({ innerText: text }), value = text => el({ innerText: text });
    const field = (l, v) => el({ querySelector: selector => (selector === '.data-label' ? label(l) : selector === '.data-value' ? value(v) : null) });
    const dd = el({ tagName: 'DD', innerText: 'Max Factory' });
    const page = {
      title: 'Frieren 1/7 - MyFigureCollection.net',
      querySelector: selector => (selector === 'h1' ? el({ innerText: 'Frieren 1/7' }) : selector === 'link[rel=canonical]' ? el({ href: 'https://myfigurecollection.net/item/1' }) : null),
      querySelectorAll: selector => ({
        'meta[property],meta[name],meta[itemprop]': [el({ attrs: { property: 'og:title' }, content: 'Frieren 1/7' })],
        'script[type="application/ld+json"]': [el({ textContent: '{"@type":"Product","name":"Frieren"}' }), el({ textContent: 'kaputt' })],
        '.data-field': [field('Origin', 'Frieren: Beyond Journey’s End'), field('Release date:', '03/27/2026  as Limited')],
        dt: [el({ innerText: 'Manufacturer', nextElementSibling: dd })],
        tr: [],
      })[selector] || [],
    };
    let opened;
    const context = vm.createContext({ document: page, location: { href: 'https://myfigurecollection.net/item/1' }, window: { open: url => { opened = url; return {}; } }, JSON, encodeURIComponent });
    vm.runInContext(code, context);
    const snapshot = JSON.parse(decodeURIComponent(opened.split('#import=')[1]));
    assert.equal(snapshot.url, 'https://myfigurecollection.net/item/1');
    assert.equal(snapshot.meta['og:title'], 'Frieren 1/7');
    assert.deepEqual(snapshot.jsonld, [{ '@type': 'Product', name: 'Frieren' }], 'a broken JSON-LD block is skipped');
    assert.deepEqual(snapshot.fields, { Origin: 'Frieren: Beyond Journey’s End', 'Release date': '03/27/2026 as Limited', Manufacturer: 'Max Factory' });
  });
});
