
import { chromium } from "@playwright/test"
const b = await chromium.launch({ headless:true })
const ctx = await b.newContext({ viewport:{width:390,height:844}, deviceScaleFactor:2, isMobile:true })
const p = await ctx.newPage()
await p.goto("https://edt-partnerships-mirror-ntsc.trycloudflare.com/?mobile=1",{waitUntil:"domcontentloaded",timeout:30000})
await p.waitForTimeout(1800)
const r = await p.evaluate(()=>{
  const cn=document.querySelector(".mvm-chips")
  if(!cn) return "NO .mvm-chips"
  const cs=getComputedStyle(cn)
  const tops=new Set(Array.from(cn.children).map(c=>Math.round(c.offsetTop)))
  return {
    containerW:Math.round(cn.offsetWidth), containerH:Math.round(cn.offsetHeight),
    flexWrap:cs.flexWrap, chips:cn.children.length,
    rows:tops.size, distinctTops:Array.from(tops),
    scrollW:cn.scrollWidth, clientW:cn.clientWidth, canScrollX:cn.scrollWidth>cn.clientWidth
  }
})
console.log("MEASURE", JSON.stringify(r))
await p.screenshot({path:"/tmp/clw/mvm-fixed-390.png", fullPage:false})
await b.close()
