import {test, expect} from '@playwright/test';

test('overview and all five comparisons work without the data service', async ({page}) => {
  const api:string[]=[];
  page.on('request', r=>{if(r.url().includes('/api/')) api.push(r.url());});
  await page.route('**/api/**',r=>r.abort());
  await page.goto('./');
  await expect(page.locator('.headline-numbers')).toContainText('63.45B');
  await expect(page.locator('.directory-table tbody tr')).toHaveCount(5);
  await expect(page.locator('.site-header nav a')).toHaveCount(3);
  await expect(page.locator('.site-footer')).toContainText('MIT licence');
  await page.getByRole('link',{name:'Compare corpora',exact:true}).click();
  await expect(page.locator('.comparison-chart .comparison-bar-row')).toHaveCount(5);
  await expect(page.locator('.source-comparison .count-badge')).toHaveText('555');
  await expect(page.locator('.quality-comparison')).toContainText('Not published');
  await page.getByLabel('Compare domain').selectOption('Legal');
  await page.locator('.domain-values>summary').click();
  await expect(page.locator('.domain-matrix tbody tr')).toHaveCount(1);
  await expect(page.locator('.source-comparison tbody tr')).not.toHaveCount(0);
  await page.getByLabel('Comparison scale',{exact:true}).selectOption('share');
  await expect(page.locator('.bar-total').first()).toContainText('%');
  await page.getByLabel('Comparison measure').selectOption('records');
  await page.getByRole('checkbox',{name:'Swedish'}).uncheck();
  await expect(page.locator('.comparison-chart .comparison-bar-row')).toHaveCount(4);
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'Export counts'}).click();
  expect((await download).suggestedFilename()).toBe('dynaword-source-comparison.csv');
  expect(api).toEqual([]);
});

test('comparison shares retain whole-corpus denominator',async({page})=>{
  await page.goto('./#compare');
  await page.getByRole('button',{name:'Legal',exact:true}).first().click();
  await page.getByLabel('Comparison scale',{exact:true}).selectOption('share');
  await expect(page.locator('.bar-total').first()).toHaveText('32.5%');
  await page.getByRole('button',{name:'Reset comparison'}).click();
  await expect(page.locator('.bar-total').first()).toHaveText('100.0%');
  await expect(page.locator('.source-comparison .count-badge')).toHaveText('555');
});

test('small screens keep content and contextual help within the viewport',async({page})=>{
  for(const width of [320,390]) {
    await page.setViewportSize({width,height:844});
    for(const route of ['overview','compare']) {
      await page.goto('./#'+route);
      await page.locator(route==='overview'?'.headline-numbers':'.comparison-bar-row').first().waitFor();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    }
    await page.locator('.domain-values>summary').click();
    await page.getByRole('button',{name:'About domain counts',exact:true}).click();
    const box=await page.locator('.context-help-content').boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x+box!.width).toBeLessThanOrEqual(width);
    await page.keyboard.press('Escape');
    await expect(page.locator('.context-help-content')).not.toBeVisible();
  }
});

test('record review tags persist locally and can be exported',async({page})=>{
  await page.goto('./#records');
  await page.locator('.record-title').first().click();
  await page.getByLabel('Review tag',{exact:true}).selectOption('quality');
  await page.keyboard.press('Escape');
  await page.locator('.record-title').first().click();
  await expect(page.getByLabel('Review tag',{exact:true})).toHaveValue('quality');
  await page.keyboard.press('Escape');
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'Export review tags'}).click();
  const artifact=await download;
  const stream=await artifact.createReadStream();const chunks:Buffer[]=[];
  for await (const chunk of stream!) chunks.push(chunk);
  const reviews=JSON.parse(Buffer.concat(chunks).toString());
  expect(reviews[0]).toMatchObject({tag:'quality',version:'v1.2.23'});
  expect(reviews[0].text).toBeUndefined();
});


test('quality graph compares labels and responds to the selected domain',async({page})=>{
  await page.goto('./#compare');
  const graph=page.locator('.quality-comparison');
  await expect(graph.locator('.comparison-bar-row')).toHaveCount(5);
  await expect(graph).toContainText('Not published');
  await graph.getByRole('button',{name:'Good',exact:true}).click();
  await expect(graph.locator('.bar-total').first()).toHaveText('37.5%');
  await expect(graph.locator('.comparison-bar-row').filter({hasText:'Swedish'}).locator('.bar-total')).toHaveText('—');
  await page.getByLabel('Annotation comparison scale').selectOption('count');
  await expect(graph.locator('.bar-total').first()).toHaveText('2.78M');
  await page.getByLabel('Compare domain').selectOption('Medical');
  await expect(graph.locator('.bar-total').first()).not.toHaveText('2.78M');
  await graph.getByRole('button',{name:'Show all categories'}).click();
  await graph.getByRole('button',{name:/Danish, Good:/}).click();
  await expect(graph.locator('.chart-readout')).toContainText('Danish · Good');
  await expect(page.locator('.coverage-section')).toHaveCount(0);
});

test('annotation field selection changes the graph and category filters',async({page})=>{
  await page.goto('./#compare');
  await page.getByLabel('Comparison annotation').selectOption('pii_presence');
  const graph=page.locator('.quality-comparison');
  await graph.getByRole('button',{name:'PII flagged',exact:true}).click();
  await expect(graph.locator('.bar-total').first()).not.toHaveText('100%');
  await page.getByLabel('Comparison annotation').selectOption('educational_value');
  await expect(graph.getByRole('button',{name:'PII flagged',exact:true})).toHaveCount(0);
  await expect(graph.getByRole('button',{name:'Show all categories'})).toHaveCount(0);
  await expect(page.getByText('These quality levels are machine predictions, not human judgements.',{exact:false})).toHaveCount(0);
});
