// format.js — the ONE TWD money formatter (display-layer SSOT, issue #25).
//
// 台幣 (TWD) 沒有小數單位：價格一律以「千分位分組的整數 + TWD 前綴」呈現,
// 永不顯示 ".00". 每一個價格顯示位 (ItemCard / PriceHistory / monitor#alertMessage)
// 都走這裡, 讓「無小數」這個合約只有單一來源。
//
// NOTE: 這是*呈現層*的 SSOT, 不是決策邏輯 SSOT. 決策 (shouldAlert / priceVerdict /
// sparkPath ...) 仍在 monitor.js, byte-unchanged.
//
// 顯示 = 依 locale 的千分位分組 (zh-TW → 逗號), 零小數 (design.md §3).
// 1069 → "1,069"; 0 / null / undefined / NaN → "0".
//
// 若 `toLocaleString('zh-TW')` 在缺乏完整 ICU 的環境退回其他行為, 測試會
// 直接斷言精確字串 "1,069" (format.test.js) 而*不會*靜默變紅以外的假綠 —— 即
// 不靠 locale engine 的「剛好對」, 靠精確期望字串把它 pin 死。
export function formatTWD(n) {
  const v = Number(n || 0)
  return v.toLocaleString('zh-TW')
}

// Prefix for display sites — keep the 幣制標記 (TWD), drop the 小數:
// 1069 → "TWD 1,069".
export function moneyTWD(n) {
  return 'TWD ' + formatTWD(n)
}
