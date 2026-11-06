// Drives the real app in a headless Chrome: every view renders, and the things people do most
// (creating a figure from a link, adding a copy, wishing, preordering until arrival, settings,
// admin) work end to end without a single error in the console.
//
//   node --test tests/frontend/
//
// Needs Chrome (CHROME_BIN overrides the lookup) and the Python requirements; set OPHIR_PYTHON
// when "python" is not the interpreter that has them.
import assert from 'node:assert/strict';
import { after, before, describe, test } from 'node:test';
import { chromePath, startBrowser, startServer } from './harness.mjs';

const MIKU = 1, TWINS = 5;
const skip = !chromePath() && !process.env.CI ? 'Chrome not found' : false;

describe('app in the browser', { skip }, () => {
  let server, page;

  before(async () => {
    server = await startServer();
    page = await startBrowser();
    await page.login(server.base, 'demo', 'figuren-1234');
  });
  after(async () => { await page?.close(); server?.stop(); });

  const noProblems = () => assert.deepEqual(page.problems.splice(0), []);
  const text = selector => page.evaluate(`document.querySelector(${JSON.stringify(selector)})?.innerText`);
  const click = selector => page.evaluate(`(document.querySelector(${JSON.stringify(selector)}).click(),1)`);
  const fill = (selector, value) => page.evaluate(`(()=>{const field=document.querySelector(${JSON.stringify(selector)});field.value=${JSON.stringify(value)};field.dispatchEvent(new Event('input'));field.dispatchEvent(new Event('change'));return 1})()`);
  // Something that saves: done says when it has. A write whose connection dropped (see
  // harness.mjs login) shows "Keine Verbindung zum Server" and changes nothing -- the app does not
  // repeat writes on its own -- so it is done once more.
  async function save(action, done, message) {
    await action();
    try {
      await page.waitFor(done, { message });
    } catch (error) {
      if (!await page.evaluate(`[...document.querySelectorAll('.toast')].some(toast=>/Keine Verbindung/.test(toast.innerText))`)) throw error;
      await action();
      await page.waitFor(done, { message });
    }
  }

  test('starts on the dashboard of the signed-in user', async () => {
    assert.equal(await text('#user-name'), 'Alex Morgan');
    assert.equal(await page.evaluate(`state.route`), 'dashboard');
    noProblems();
  });

  test('every view renders', async () => {
    for (const route of ['catalog', 'collection', 'watchlist', 'preorders', 'settings', 'dashboard']) {
      await page.route(route);
      assert.equal(await page.evaluate(`document.body.dataset.route`), route);
      assert.ok(await page.evaluate(`document.querySelector('#content').innerText.trim().length>20`), `${route} is empty`);
      assert.deepEqual(page.problems.splice(0), [], route);
    }
  });

  test('the catalogue filters and opens a figure', async () => {
    await page.route('catalog');
    assert.equal(await page.evaluate(`document.querySelectorAll('.fig-tile').length`), 5);
    await page.evaluate(`(()=>{const select=document.querySelector('[data-filter="series"]');select.value='Re:Zero';select.dispatchEvent(new Event('change'));return 1})()`);
    await page.waitFor(`document.querySelectorAll('.fig-tile').length===2`, { message: 'the series filter' });
    await click(`.fig-tile[data-figure="${TWINS}"]`);
    await page.waitFor(`!document.querySelector('#figure-modal').classList.contains('hidden')&&document.querySelector('#figure-dialog h2')?.innerText.includes('Twins')`);
    for (const tab of ['preorders', 'value', 'lists', 'info', 'copies']) {
      await click(`[data-figure-tab="${tab}"]`);
      await page.waitFor(`document.querySelector('[data-figure-tab="${tab}"]').classList.contains('active')`);
    }
    await page.evaluate(`(closeOverlay('figure-modal'),state.catalogFilters=defaultCatalogFilters(),1)`);
    noProblems();
  });

  test('the catalogue groups by franchise, brand, manufacturer or line and opens a group', async () => {
    await page.route('catalog');
    await click('[data-group-by="series"]');
    await page.waitFor(`document.querySelectorAll('.fig-group-tile').length===4`, { message: 'the franchise groups' });
    assert.equal(await page.evaluate(`document.querySelector('[data-filter="series"]')`), null, 'no franchise filter while showing franchises');
    assert.match(await text('.fig-count'), /4 Franchises · 5 Figuren/);
    await click('.fig-group-tile[data-group="Re:Zero"]');
    await page.waitFor(`document.querySelectorAll('.fig-tile').length===2&&document.querySelector('.fig-group-head h2')?.innerText==='Re:Zero'`, { message: 'the open group' });
    assert.equal(await page.evaluate(`document.querySelector('[data-filter="series"]').value`), 'Re:Zero');
    assert.equal(await page.evaluate(`document.querySelector('[data-filter-reset]')`), null, 'the open group is no filter to reset');
    await click('[data-group-back]');
    await page.waitFor(`document.querySelectorAll('.fig-group-tile').length===4&&!document.querySelector('.fig-group-head')`, { message: 'back to the groups' });

    await click('[data-group-by="brand"]');
    await page.waitFor(`document.querySelector('.fig-hint')&&document.querySelectorAll('.fig-group-tile').length===1`, { message: 'the hint that no figure has a brand' });
    await click('.fig-group-tile');
    await page.waitFor(`document.querySelectorAll('.fig-tile').length===5&&document.querySelector('.fig-group-head h2')?.innerText==='Ohne Marke'`, { message: 'the figures without a brand' });

    await click('[data-group-by="line"]');
    await page.waitFor(`document.querySelectorAll('.fig-group-tile').length===4&&document.querySelector('.fig-group-tile:last-child')?.innerText.includes('Ohne Linie')`, { message: 'figures without a line last' });
    await page.evaluate(`(()=>{const select=document.querySelector('[data-group-sort]');select.value='count';select.dispatchEvent(new Event('change'));return 1})()`);
    await page.waitFor(`document.querySelector('[data-group-sort]')?.value==='count'&&document.querySelector('.fig-group-tile:last-child')?.innerText.includes('Ohne Linie')`, { message: 'the groups by size' });
    await page.waitFor(`JSON.stringify(state.boot.settings.groupings)==='{"catalog":"line","collection":"","watch":""}'`, { message: 'the kind to be remembered' });

    await click('[data-group-by=""]');
    await page.waitFor(`document.querySelectorAll('.fig-tile').length===5&&document.querySelector('[data-group-by=""]').classList.contains('active')`, { message: 'the figures again' });
    noProblems();
  });

  test('a line preset starts from the catalogue, completes its figures and fills the form', async () => {
    await page.route('catalog');
    await click('#catalog-presets');
    await page.waitFor(`document.querySelector('#line-presets [data-line-create]')`, { message: 'the presets dialog with the lines that have none' });
    assert.match(await text('#line-presets'), /Noch keine Vorlage[\s\S]*figma/);
    await page.evaluate(`([...document.querySelectorAll('#line-presets .fig-preset-row')].find(row=>row.innerText.startsWith('figma')).querySelector('[data-line-create]').click(),1)`);
    await page.waitFor(`document.querySelector('#preset-form [data-field="manufacturer"]')?.value==='Max Factory'`, { message: "the preset to start from what the line's figures say" });
    assert.equal(await page.evaluate(`document.querySelector('#preset-form [data-field="category"]').value`), 'figma');
    await fill('#preset-form [data-field="brand"]', 'Good Smile Company');
    await save(() => click('#preset-save'), `!document.querySelector('#preset-form')&&document.querySelector('#line-presets [data-preset-apply]')`, 'the preset in the list, its figure incomplete');
    await save(() => click('#line-presets [data-preset-apply]'), `!document.querySelector('#line-presets [data-preset-apply]')`, "the line's figures completed");
    assert.equal(await page.evaluate(`api('/api/figures/3').then(figure=>figure.brand)`), 'Good Smile Company');
    await page.evaluate(`(closeDialog(),1)`);

    await page.evaluate(`(openFigureForm(),1)`);
    await page.waitFor(`document.querySelector('#figure-form [data-field="line"]')`);
    await fill('#figure-form [data-field="manufacturer"]', '');
    await fill('#figure-form [data-field="line"]', 'FIGMA');
    await page.waitFor(`document.querySelector('#figure-form [data-field="manufacturer"]').value==='Max Factory'`, { message: 'the preset to fill the form' });
    assert.deepEqual(await page.evaluate(`['brand','category','scale'].map(key=>document.querySelector('#figure-form [data-field="'+key+'"]').value)`), ['Good Smile Company', 'figma', 'Non-Scale']);
    assert.match(await text('#preset-hint'), /Vorlage „figma“ – übernommen: Marke, Hersteller, Kategorie, Maßstab/);
    await fill('#figure-form [data-field="manufacturer"]', 'Good Smile Company');
    await fill('#figure-form [data-field="line"]', 'Nendoroid');
    await page.waitFor(`/Keine Vorlage für „Nendoroid“/.test(document.querySelector('#preset-hint').innerText)`, { message: 'the offer to save a preset' });
    assert.equal(await page.evaluate(`document.querySelector('#figure-form [data-field="manufacturer"]').value`), 'Good Smile Company', 'a typed value stays');
    await fill('#figure-form [data-field="line"]', 'figma');
    await page.waitFor(`/Anders als in der Vorlage: Hersteller/.test(document.querySelector('#preset-hint').innerText)`, { message: 'the typed manufacturer kept and named' });
    await click('#preset-hint [data-preset-take]');
    await page.waitFor(`document.querySelector('#figure-form [data-field="manufacturer"]').value==='Max Factory'`);
    await page.evaluate(`(closeDialog(),1)`);
    noProblems();
  });

  test('a figure is created from a link and put into the collection', async () => {
    await page.evaluate(`(openFigureForm(),1)`);
    await page.waitFor(`document.querySelector('#import-url')`);
    assert.match(await page.evaluate(`document.querySelector('#figure-image-file').accept`), /image\/avif/);
    await fill('#import-url', 'https://shop.test/saber');
    await click('#import-fetch');
    await page.waitFor(`document.querySelector('[data-field="name"]').value==='Saber Alter 1/7'`, { message: 'the link import to fill the form' });
    assert.equal(await page.evaluate(`document.querySelector('[data-field="jan"]').value`), '4560228200001');
    await page.evaluate(`(document.querySelector('#figure-after').value='copy',1)`);
    await save(() => click('#figure-save'), `document.querySelector('#entry-dialog')`, 'the copy dialog after saving');
    await fill('#entry-dialog [data-field="purchase_price"]', '159,90');
    await save(() => click('#entry-save'), `!document.querySelector('#entry-dialog')&&state.modalFigure?.owned===1`, 'the copy to be saved');
    await page.evaluate(`(closeOverlay('figure-modal'),1)`);
    await page.route('collection');
    const collection = await text('#content');
    assert.ok(collection.includes('Saber Alter 1/7'), collection);
    noProblems();
  });

  test('wishing, preordering and the arrival booked into the collection', async () => {
    await page.route('catalog');
    await save(() => click(`.fig-tile[data-figure="${MIKU}"] [data-wish]:not(.active)`), `state.boot.counts.wished===1`, 'the wish to count');
    await page.evaluate(`(openFigure(${MIKU}),1)`);
    await page.waitFor(`state.modalFigure?.id===${MIKU}`);
    await click('[data-figure-action="preorder"]');
    await page.waitFor(`document.querySelector('#preorder-dialog')`);
    await fill('#preorder-dialog [data-field="price"]', '199');
    await fill('#preorder-dialog [data-field="shop"]', 'AmiAmi');
    await save(() => click('#preorder-save'), `!document.querySelector('#preorder-dialog')&&state.modalFigure?.preorders?.length===1`, 'the preorder to be saved');
    assert.equal(await page.evaluate(`state.modalFigure.wished`), false, 'ordering took it off the wishlist');
    await page.evaluate(`(closeOverlay('figure-modal'),1)`);
    await page.route('preorders');
    await save(() => page.evaluate(`(()=>{const select=document.querySelector('[data-status]');select.value='delivered';select.dispatchEvent(new Event('change'));return 1})()`),
      `state.boot.counts.preorders===0&&state.boot.counts.collection===2`, 'the arrival to be booked');
    noProblems();
  });

  test('settings save the appearance and the public profile', async () => {
    await page.route('settings');
    await click('[data-mobile-appearance="light"]');
    await page.waitFor(`document.body.classList.contains('mobile-light')`);
    await page.waitFor(`document.querySelector('#public-slug')`);
    await fill('#public-slug', 'alex');
    await page.evaluate(`(document.querySelector('#public-enabled').checked=true,1)`);
    await save(() => click('#public-save'), `document.querySelector('#public-profile-body a[href$="/u/alex"]')`, 'the public link');
    await click('[data-mobile-appearance="dark"]');
    noProblems();
  });
});

describe('admin in the browser', { skip }, () => {
  let server, page;
  before(async () => { server = await startServer(); page = await startBrowser(); await page.login(server.base, 'admin', 'admin'); });
  after(async () => { await page?.close(); server?.stop(); });

  test('the admin view lists accounts and the catalogue', async () => {
    await page.route('admin');
    await page.waitFor(`document.querySelector('#admin-catalog-body')?.innerText.includes('Figuren im Katalog')`);
    assert.ok((await page.evaluate(`document.querySelector('#content').innerText`)).includes('demo'));
    assert.deepEqual(page.problems.splice(0), []);
  });
});

// The homelab serves the app under /figures (Traefik strips it and names it in X-Forwarded-Prefix):
// every address the page asks for has to carry it, or the request lands outside the app.
describe('the app under a path prefix', { skip }, () => {
  let server, page;
  before(async () => {
    server = await startServer({ prefix: '/figures' });
    page = await startBrowser();
    await page.login(server.base, 'demo', 'figuren-1234');
  });
  after(async () => { await page?.close(); server?.stop(); });

  test('views, a figure, the bookmarklet and a public profile stay under the prefix', async () => {
    for (const route of ['catalog', 'collection', 'watchlist', 'preorders', 'settings', 'dashboard']) await page.route(route);
    await page.route('catalog');
    assert.equal(await page.evaluate(`document.querySelectorAll('.fig-tile').length`), 5);
    await page.evaluate(`(document.querySelector('.fig-tile[data-figure="${MIKU}"]').click(),1)`);
    await page.waitFor(`!document.querySelector('#figure-modal').classList.contains('hidden')`, { message: 'the figure dialog' });
    await page.evaluate(`(closeOverlay('figure-modal'),1)`);
    assert.ok(decodeURIComponent(await page.evaluate(`bookmarkletHref()`)).includes(`${server.base}/#import=`), 'the bookmarklet opens the app under the prefix');

    await page.evaluate(`api('/api/account/public-profile',{method:'PUT',body:JSON.stringify({enabled:true,slug:'alex'})})`);
    await page.goto(`${server.base}/u/alex`);
    await page.waitFor(`document.querySelector('.public-head')`, { message: 'the public profile to load' });

    const origin = new URL(server.base).origin;
    assert.deepEqual(page.requests.filter(url => url.startsWith(origin) && !url.startsWith(`${server.base}/`)), []);
    assert.deepEqual(page.problems.splice(0), []);
  });
});
