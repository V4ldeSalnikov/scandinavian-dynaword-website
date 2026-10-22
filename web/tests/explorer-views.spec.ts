import {test,expect} from '@playwright/test';

for(const language of ['danish','norwegian','swedish','icelandic','faroese']) {
 test(`${language} shares flags, selection charts and source details`,async({page})=>{
  test.setTimeout(120000);
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`./#records?language=${language}`);
  const names:Record<string,string>={danish:'Denmark',norwegian:'Norway',swedish:'Sweden',icelandic:'Iceland',faroese:'Faroe Islands'};
  await expect(page.locator('.dataset-selector').getByRole('img',{name:`${names[language]} flag`})).toBeVisible();
  await page.getByRole('button',{name:'Selection statistics',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Understand your selection'})).toBeVisible();
  await expect(page.locator('.metrics')).toHaveAttribute('aria-busy','false');
  await expect(page.locator('.metrics .metric').first().locator('strong')).not.toHaveText('—');
  await expect(page.getByRole('heading',{name:'Corpus composition',exact:true})).toBeVisible();
  await expect(page.locator('.composition canvas')).toBeVisible();
  await page.getByRole('button',{name:'By source',exact:true}).click();
  await page.getByRole('button',{name:'Records',exact:true}).last().click();
  if(language==='swedish'){
   await expect(page.getByLabel('Annotation to visualise')).toBeDisabled();
   await expect(page.locator('.annotations')).toContainText('Annotations are not published');
  } else {
   await page.getByLabel('Annotation to visualise').selectOption('pii_presence');
   await expect(page.locator('.metrics')).toHaveAttribute('aria-busy','false');
   await page.getByLabel('Filter by chart annotation category').selectOption('no_pii');
   await expect(page.locator('.filter-chips')).toContainText('No PII flagged');
   await expect(page.locator('.metrics')).toHaveAttribute('aria-busy','false');
   await expect(page.locator('.lengths canvas')).toBeVisible();
   await page.getByRole('button',{name:'Reset filters',exact:true}).click();
  }
  await page.getByRole('button',{name:'Source details',exact:true}).click();
  await expect(page.locator('.source-card').first()).toBeVisible();
  const card=page.locator('.source-card').first();
  const name=await card.locator('h3').innerText();
  await card.click();
  await expect(page.getByRole('dialog')).toHaveAccessibleName(name);
  await expect(page.getByRole('link',{name:'Read source documentation'})).toHaveAttribute('href',/huggingface.co/);
  await page.keyboard.press('Escape');
  await expect(card).toBeFocused();
  await card.click();
  await page.getByRole('button',{name:'Explore this source',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('.explorer-tabs button').first()).toHaveAttribute('aria-current','page');
  await expect(page.locator('.filter-chips')).not.toBeEmpty();
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Selection statistics',exact:true}).click();
  await expect(page.locator('.metrics')).toHaveAttribute('aria-busy','false');
  await expect(page.locator('.record-language-row .country-flag')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(390);
  await page.screenshot({path:`../.cache/unified-${language}-mobile.png`,fullPage:true});
  await page.getByRole('button',{name:'Source details',exact:true}).click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(390);
  await page.locator('.source-card').first().click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(390);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(errors).toEqual([]);
 });
}

test('statistics failures have a retry and do not display an old selection',async({page})=>{
 let fail=true;
 await page.route('**/api/corpora/faroese/stats?**',route=>fail?route.fulfill({status:503,json:{detail:'Statistics are temporarily unavailable.'}}):route.continue());
 await page.goto('./#records?language=faroese');
 await page.getByRole('button',{name:'Selection statistics',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Statistics are temporarily unavailable.');
 fail=false;
 await page.getByRole('button',{name:'Retry',exact:true}).click();
 await expect(page.locator('.metrics')).toHaveAttribute('aria-busy','false');
 await expect(page.getByRole('alert')).toHaveCount(0);
});

test('switching views retains loaded pages and distinct rows with repeated document IDs',async({page})=>{
 await page.route('**/api/corpora/faroese/**',route=>{
  const url=new URL(route.request().url());
  if(url.pathname.endsWith('/search-status'))return route.fulfill({json:{text:false,semantic:false}});
  if(url.pathname.endsWith('/stats'))return route.fulfill({json:{totals:{records:60,tokens:600,sources:1,annotated:0},sources:[],domains:[],annotations:[],histogram:[],annotation_covered:0,annotation:'content_quality'}});
  const offset=Number(url.searchParams.get('offset')||0);
  return route.fulfill({json:{rows:Array.from({length:30},(_,i)=>({id:'repeated-id',record_no:offset+i,source:'wikipedia',domain:'Encyclopedic',token_count:10,preview:`Record ${offset+i}`,config:'wikipedia',row_index:offset+i,annotations_available:false})),total:60,has_more:offset===0,next_offset:offset+30}});
 });
 await page.goto('./#records?language=faroese');
 await expect(page.locator('.record-table tbody tr')).toHaveCount(30);
 await page.getByRole('button',{name:'Load more records',exact:true}).click();
 await expect(page.locator('.record-table tbody tr')).toHaveCount(60);
 await page.getByRole('button',{name:'Selection statistics',exact:true}).click();
 await page.locator('.explorer-tabs').getByRole('button',{name:'Records',exact:true}).click();
 await expect(page.locator('.record-table tbody tr')).toHaveCount(60);
});
