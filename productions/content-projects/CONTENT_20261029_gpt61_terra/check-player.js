async page => {
  const video=page.locator('video');
  await video.evaluate(v => new Promise((resolve,reject) => {
    if(v.readyState>=1) return resolve();
    v.addEventListener('loadedmetadata',resolve,{once:true});
    v.addEventListener('error',reject,{once:true});
  }));
  const result=await video.evaluate(v=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight,readyState:v.readyState,error:v.error?.code||null}));
  await video.evaluate(v=>{v.currentTime=23;});
  await page.screenshot({path:'outputs/content-projects/CONTENT_20261029_gpt61_terra/v01/review/browser-player.png'});
  return result;
}
