
import { chromium } from '@playwright/test'
const url = "https://edt-partnerships-mirror-ntsc.trycloudflare.com/?mobile=1"
const out = "/tmp/clw/mvm-mobile-390.png"
let b
try {
  b = await chromium.launch({ headless: true })
} catch(e) { console.log("LAUNCH-ERR", String(e).slice(0,200)); process.exit(3) }
const ctx = await b.newContext({ viewport:{width:390,height:844}, deviceScaleFactor:2, isMobile:true })
const p = await ctx.newPage()
try { await p.goto(url,{waitUntil:"domcontentloaded",timeout:30000}) } catch(e){console.log("goto-err",String(e).slice(0,100))}
await p.waitForTimeout(1800)
const info = await p.evaluate(()=>{const cn=document.querySelector(".mvm-chips");return {chips:document.querySelectorAll(".mvm-chip").length,scrollW:cn?cn.scrollWidth:-1,clientW:cn?cn.clientWidth:-1,snap:cn?getComputedStyle(cn).scrollSnapType:"none"};})
console.log("INFO",JSON.stringify(info))
try { await p.screenshot({path:out,fullPage:false}); console.log("OK",out) } catch(e){ console.log("SHOT-ERR",String(e).slice(0,150)) }
await b.close()
