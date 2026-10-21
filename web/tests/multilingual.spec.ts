import {test,expect} from '@playwright/test';

test('all additional languages support full browsing, pagination and original text',async({page})=>{
  test.setTimeout(180000);
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  for(const language of ['norwegian','swedish','icelandic','faroese']){
    await page.goto('./#records?language='+language);
    await expect(page.getByLabel('Explorer language')).toHaveValue(language);
    await expect(page.locator('.record-table tbody tr')).toHaveCount(30,{timeout:60000});
    await page.getByRole('button',{name:'Load more records',exact:true}).click();
    await expect(page.locator('.record-table tbody tr')).toHaveCount(60,{timeout:60000});
    await page.locator('.record-title').first().click();
    await expect(page.locator('.reader-text')).not.toBeEmpty({timeout:60000});
    await page.getByRole('button',{name:'Metadata & annotations'}).click();
    await expect(page.locator('.remote-metadata')).toContainText('Token count');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});

test('Swedish can browse to the last corpus row',async({page})=>{
  await page.goto('./#records?language=swedish');
  await expect(page.locator('.record-title').first()).toBeVisible();
  await page.getByLabel('Go to record number').fill('551087777');
  await page.getByRole('button',{name:'Go',exact:true}).click();
  await expect(page.locator('.record-table tbody tr')).toHaveCount(1);
  await expect(page.getByRole('button',{name:'Load more records',exact:true})).toHaveCount(0);
});

test('mobile multilingual explorer keeps filters and reader accessible',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('./#records?language=faroese');
  await expect(page.locator('.record-title').first()).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(390);
  await page.getByRole('button',{name:'Open filters',exact:true}).click();
  await expect(page.getByLabel('Annotation field',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Close filters',exact:true}).last().click();
  await expect(page.locator('.sidebar')).not.toBeVisible();
  await page.locator('.record-title').first().click();
  await expect(page.locator('.reader-text')).not.toBeEmpty();
  await page.keyboard.press('Escape');
  await expect(page.locator('.record-title').first()).toBeFocused();
});

test('Norwegian annotation fields intersect and are reflected in the reader',async({page})=>{
  await page.goto('./#records?language=norwegian');
  await page.getByLabel('Annotation field',{exact:true}).selectOption('content_integrity');
  await page.getByLabel('Annotation value',{exact:true}).selectOption('complete');
  await page.getByLabel('Annotation field',{exact:true}).selectOption('pii_presence');
  await page.getByLabel('Annotation value',{exact:true}).selectOption('no_pii');
  await expect(page.locator('.filter-chips button')).toHaveCount(2);
  await expect(page.locator('.record-title').first()).toBeVisible({timeout:60000});
  await page.locator('.record-title').first().click();
  await page.getByRole('button',{name:'Metadata & annotations'}).click();
  await expect(page.locator('.remote-metadata')).toContainText('complete');
  await expect(page.locator('.remote-metadata')).toContainText('no_pii');
});
