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

  test('a figure is created from a link and put into the collection', async () => {
    await page.evaluate(`(openFigureForm(),1)`);
    await page.waitFor(`document.querySelector('#import-url')`);
    await fill('#import-url', 'https://shop.test/saber');
    await click('#import-fetch');
    await page.waitFor(`document.querySelector('[data-field="name"]').value==='Saber Alter 1/7'`, { message: 'the link import to fill the form' });
    assert.equal(await page.evaluate(`document.querySelector('[data-field="jan"]').value`), '4560228200001');
    await page.evaluate(`(document.querySelector('#figure-after').value='copy',1)`);
    await click('#figure-save');
    await page.waitFor(`document.querySelector('#entry-dialog')`, { message: 'the copy dialog after saving' });
    await fill('#entry-dialog [data-field="purchase_price"]', '159,90');
    await click('#entry-save');
    await page.waitFor(`!document.querySelector('#entry-dialog')&&state.modalFigure?.owned===1`, { message: 'the copy to be saved' });
    await page.evaluate(`(closeOverlay('figure-modal'),1)`);
    await page.route('collection');
    assert.ok((await text('#content')).includes('Saber Alter 1/7'));
    noProblems();
  });

  test('wishing, preordering and the arrival booked into the collection', async () => {
    await page.route('catalog');
    await click(`.fig-tile[data-figure="${MIKU}"] [data-wish]`);
    await page.waitFor(`state.boot.counts.wished===1`, { message: 'the wish to count' });
    await page.evaluate(`(openFigure(${MIKU}),1)`);
    await page.waitFor(`state.modalFigure?.id===${MIKU}`);
    await click('[data-figure-action="preorder"]');
    await page.waitFor(`document.querySelector('#preorder-dialog')`);
    await fill('#preorder-dialog [data-field="price"]', '199');
    await fill('#preorder-dialog [data-field="shop"]', 'AmiAmi');
    await click('#preorder-save');
    await page.waitFor(`!document.querySelector('#preorder-dialog')&&state.modalFigure?.preorders?.length===1`);
    assert.equal(await page.evaluate(`state.modalFigure.wished`), false, 'ordering took it off the wishlist');
    await page.evaluate(`(closeOverlay('figure-modal'),1)`);
    await page.route('preorders');
    await page.evaluate(`(()=>{const select=document.querySelector('[data-status]');select.value='delivered';select.dispatchEvent(new Event('change'));return 1})()`);
    await page.waitFor(`state.boot.counts.preorders===0&&state.boot.counts.collection===2`, { message: 'the arrival to be booked' });
    noProblems();
  });

  test('settings save the appearance and the public profile', async () => {
    await page.route('settings');
    await click('[data-mobile-appearance="light"]');
    await page.waitFor(`document.body.classList.contains('mobile-light')`);
    await page.waitFor(`document.querySelector('#public-slug')`);
    await fill('#public-slug', 'alex');
    await page.evaluate(`(document.querySelector('#public-enabled').checked=true,1)`);
    await click('#public-save');
    await page.waitFor(`document.querySelector('#public-profile-body a[href$="/u/alex"]')`, { message: 'the public link' });
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
