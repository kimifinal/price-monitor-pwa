"""Offline snapshot of Costco 3C + 家電 PDP prices.

Refreshed 2026-11-11 via BFS crawl of Costco PDP "相關推薦" links
(20 家電 + 11 3C items, all real SKUs).
Used by the API (live=False default) and by the offline unit tests so CI stays
offline-safe and free of 429 limits.
"""

import os as _os

# JSON literal = valid Python (strings/numbers/lists). null never appears here
# because defaults fill every field.
DEMO_BASKET = [
  {
    "name": "Klipsch The Three Plus 藍牙喇叭",
    "price": 9499.0,
    "currency": "TWD",
    "sku": "147407",
    "url": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Bluetooth-Speakers-Landline-Phones/Klipsch-The-Three-Plus-Bluetooth-Speaker/p/147407",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Bluetooth-Speakers-Landline-Phones/Klipsch-The-Three-Plus-Bluetooth-Speaker/p/147407"
  },
  {
    "name": "JBL Live 670NC 耳罩式降噪藍牙耳機",
    "price": 1899.0,
    "currency": "TWD",
    "sku": "153876",
    "url": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/JBL-Live-670NC-Over-ear-Noise-Cancelling-Bluetooth-Headphones/p/153876",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/JBL-Live-670NC-Over-ear-Noise-Cancelling-Bluetooth-Headphones/p/153876"
  },
  {
    "name": "Acer Swift Air 14吋 AI 輕薄筆記型電腦 SFA14-55M-55EQ",
    "price": 23899.0,
    "currency": "TWD",
    "sku": "163472",
    "url": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Laptops/Acer-Swift-Air-14-inch-AI-Lightweight-Notebook-SFA14-55M-55EQ/p/163472",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Laptops/Acer-Swift-Air-14-inch-AI-Lightweight-Notebook-SFA14-55M-55EQ/p/163472"
  },
  {
    "name": "Klipsch GIG XL 藍牙派對音響 含Fiesta有線麥克風",
    "price": 3489.0,
    "currency": "TWD",
    "sku": "162860",
    "url": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Bluetooth-Speakers-Landline-Phones/Klipsch-GIG-XL-Bluetooth-Party-Speaker-with-Fiesta-Wired-Microphone/p/162860",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Bluetooth-Speakers-Landline-Phones/Klipsch-GIG-XL-Bluetooth-Party-Speaker-with-Fiesta-Wired-Microphone/p/162860"
  },
  {
    "name": "Klipsch Nashville 無線藍牙喇叭",
    "price": 3999.0,
    "currency": "TWD",
    "sku": "147410",
    "url": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Bluetooth-Speakers-Landline-Phones/Klipsch-Nashville-Portable-Bluetooth-Speaker/p/147410",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Bluetooth-Speakers-Landline-Phones/Klipsch-Nashville-Portable-Bluetooth-Speaker/p/147410"
  },
  {
    "name": "Swann 4K 槍型智能 IP攝影機",
    "price": 4395.0,
    "currency": "TWD",
    "sku": "145805",
    "url": "https://www.costco.com.tw/Digital-Mobile/Cameras/Security-Cameras-Drones/Swann-Professional-4K-Heat-Motion-Sensing-IP-Add-on-Bullet-Camera/p/145805",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Cameras/Security-Cameras-Drones/Swann-Professional-4K-Heat-Motion-Sensing-IP-Add-on-Bullet-Camera/p/145805"
  },
  {
    "name": "Backbone Mamba 人體工學全網椅",
    "price": 4599.0,
    "currency": "TWD",
    "sku": "144129",
    "url": "https://www.costco.com.tw/Furniture-Kitchen/Furniture/Computer-Desk-Chair-Sets/Backbone-Mamba-Mesh-Ergonomic-Chair/p/144129",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Furniture-Kitchen/Furniture/Computer-Desk-Chair-Sets/Backbone-Mamba-Mesh-Ergonomic-Chair/p/144129"
  },
  {
    "name": "SteelSeries 賽睿 Apex 7 TKL 有線電競鍵盤(紅軸) 英文",
    "price": 1869.0,
    "currency": "TWD",
    "sku": "157688",
    "url": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Keyboards-Mice-Computer-Accessories/SteelSeries-Apex-7-TKL-RGB-Wired-Gaming-Keyboard-Red-Switch-English/p/157688",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Keyboards-Mice-Computer-Accessories/SteelSeries-Apex-7-TKL-RGB-Wired-Gaming-Keyboard-Red-Switch-English/p/157688"
  },
  {
    "name": "Philips Hi-fi 頭戴式藍牙耳機 TAH5209BK",
    "price": 2289.0,
    "currency": "TWD",
    "sku": "153489",
    "url": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/Philips-Hi-fi-Over-ear-Wireless-Bluetooth-Headphones-TAH5209BK/p/153489",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/Philips-Hi-fi-Over-ear-Wireless-Bluetooth-Headphones-TAH5209BK/p/153489"
  },
  {
    "name": "ANKER A2674 336 GaN 67W 急速充電器 2入組",
    "price": 1069.0,
    "currency": "TWD",
    "sku": "149699",
    "url": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/ANKER-A2674-336-GaN-67W-Charger-2-Pack/p/149699",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/ANKER-A2674-336-GaN-67W-Charger-2-Pack/p/149699"
  },
  {
    "name": "HP 14吋筆記型電腦 EliteBook 6 G1q",
    "price": 29999.0,
    "currency": "TWD",
    "sku": "160448",
    "url": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Laptops/HP-14-inch-Laptop-EliteBook-6-G1q/p/160448",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Laptops/HP-14-inch-Laptop-EliteBook-6-G1q/p/160448"
  },
  {
    "name": "BOSE Solo Soundbar 電視音響 II",
    "price": 8149.0,
    "currency": "TWD",
    "sku": "3062725",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/BOSE-Solo-Soundbar-TV-Speaker-II/p/3062725",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "飛利浦 55吋 4K QLED Google TV 顯示器 55PQT8530/96",
    "price": 12599.0,
    "currency": "TWD",
    "sku": "153526",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Television/Philips-55-inch-4K-UHD-Smart-TV/p/153526",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "Honeywell 淨味空氣清淨機 HPA5350WTWV1",
    "price": 6999.0,
    "currency": "TWD",
    "sku": "157137",
    "url": "https://www.costco.com.tw/Televisions-Appliances/Air-Conditioners-Fans/Coolers-Humidifiers/Honeywell-Air-Purifier-AC1025D/p/157137",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "TCL 75吋 4K Mini LED Google TV 量子智能液晶顯示器 不含視訊盒 75C6K | Cos...",
    "price": 27799.0,
    "currency": "TWD",
    "sku": "153555",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/70-79-TVs/TCL-75-inch-4K-Mini-LED-Google-TV-Smart-Monitor-without-Tuner-Box-75C6K/p/153555",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "JBL BAR 2.1 DEEP BASS (MK2) 2.1聲道條型音箱",
    "price": 9699.0,
    "currency": "TWD",
    "sku": "154155",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/JBL-BAR-21-DEEP-BASS-MK2-Channel-Soundbar-With-Wireless-Subwoofer/p/154155",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "Samsung 3.1聲道 兩件式家庭劇院含重低音 HW-S700D/ZW",
    "price": 9999.0,
    "currency": "TWD",
    "sku": "149115",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Samsung-31Ch-Ultra-Slim-Soundbar-HW-S700DZW/p/149115",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "飛利浦 2.1 聲道 無線重低音杜比全景聲聲霸 TAB6309",
    "price": 7599.0,
    "currency": "TWD",
    "sku": "147918",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Philips-21-CH-Soundbar-TAB6309/p/147918",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "Sony 3.1聲道 BRAVIA Theatre Bar 5 單件式喇叭搭配無線重低音揚聲器 HT-B500 |...",
    "price": 11949.0,
    "currency": "TWD",
    "sku": "162420",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Sony-31-Channel-BRAVIA-Theatre-Bar-5-Soundbar-with-Wireless-Subwoofer-HT-B500/p/162420",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "Klipsch Flexus 無線聲霸 Core 100",
    "price": 9999.0,
    "currency": "TWD",
    "sku": "148022",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Klipsch-Flexus-Soundbar-Core-100/p/148022",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "DeWALT 得偉 乾濕兩用吸塵器",
    "price": 3399.0,
    "currency": "TWD",
    "sku": "6677010",
    "url": "https://www.costco.com.tw/Televisions-Appliances/Small-Appliances/Vacuums-Floor-Care/DeWALT-DryWet-Vacuum/p/6677010",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "國際牌 手持式掛燙機 NI-GS410",
    "price": 2449.0,
    "currency": "TWD",
    "sku": "152206",
    "url": "https://www.costco.com.tw/Televisions-Appliances/Small-Appliances/Sewing-Garment-Care/Panasonic-Handheld-Fabric-Steamer-NI-GS410/p/152206",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "飛利浦 55吋 4K Google TV 顯示器 55PUH7630/96",
    "price": 13699.0,
    "currency": "TWD",
    "sku": "153519",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/Philips-55-inch-4K-Google-TV-Monitor-55PUH763096/p/153519",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "Samsung 55吋 Mini LED 4K AI 量子智慧顯示器 UA55M1EHAXXZW | Costco...",
    "price": 18999.0,
    "currency": "TWD",
    "sku": "161520",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/Samsung-55-inch-Mini-LED-4K-AI-Smart-Monitor-UA55M1EHAXXZW/p/161520",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "東芝 Regza 55型 QLED144Hz 全陣列背光智慧顯示器 55Z670NT",
    "price": 18999.0,
    "currency": "TWD",
    "sku": "156638",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/Toshiba-Regza-55-inch-Full-Array-QLED-144Hz-Smart-Monitor-55Z670NT/p/156638",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "TCL 55吋 P6L 4K Google TV 智慧連網液晶顯示器 不含視訊盒 55P6L",
    "price": 13299.0,
    "currency": "TWD",
    "sku": "161741",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/TCL-55-inch-P6L-4K-Google-TV-Smart-Monitor-without-Tuner-Box-55P6L/p/161741",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "Looploop 固定式電視架 EF90 適用40~100吋電視",
    "price": 789.0,
    "currency": "TWD",
    "sku": "145781",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/Looploop-Fixed-TV-Wall-Mount-EF90-Apply-to-40-inch-100-inch-TV/p/145781",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "US Brown Bear壁掛架 VC6B80 適用40吋~80吋電視",
    "price": 1019.0,
    "currency": "TWD",
    "sku": "119117",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/US-Brown-Bear-TV-Arm-VC6B80-Apply-to-40-inch-80-inch-TV/p/119117",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "TCL Q85H 7.1.4聲道 Dolby Atmos 重低音旗艦級家庭劇院聲霸",
    "price": 22999.0,
    "currency": "TWD",
    "sku": "154771",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/TCL-Q85H-714-Channel-Dolby-Atmos-Soundbar-with-Wireless-Subwoofer-and-Satellite-Speakers/p/154771",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "Looploop H100 多角度調整電視架",
    "price": 1099.0,
    "currency": "TWD",
    "sku": "156943",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/Looploop-H100-Full-Motion-TV-Mount/p/156943",
    "tag": "家電",
    "category_path": ""
  },
  {
    "name": "飛利浦 86吋 4K QLED Google TV 顯示器 86PQT8530/96",
    "price": 39999.0,
    "currency": "TWD",
    "sku": "153524",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/80-Above-TVs/Philips-86-inch-4K-QLED-Google-TV-Monitor-86PQT853096/p/153524",
    "tag": "家電",
    "category_path": ""
  }
]

__all__ = ["DEMO_BASKET"]
