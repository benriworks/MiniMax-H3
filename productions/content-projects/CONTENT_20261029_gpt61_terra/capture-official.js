async page => {
  await page.setViewportSize({width:1600,height:1100});
  await page.evaluate(() => {document.body.style.zoom='2';});
  const h=page.getByRole('heading',{name:'Use GPT-6.1 Terra for visual reasoning and computer use Copy link to Use GPT-6.1 Terra for visual reasoning and computer use'});
  await h.screenshot({path:'outputs/content-projects/CONTENT_20261029_gpt61_terra/v01/official-heading.png'});
}
