"""Offline snapshot of Costco 3C + 家電 PDP prices.

Refreshed 2026-11-12 via BFS crawl of Costco PDP "相關推薦" links
(15 家電 + 15 3C items, all real SKUs).
Used by the API (live=False default) and by the offline unit tests so CI stays
offline-safe and free of 429 limits.
"""

import os as _os

# JSON literal = valid Python (strings/numbers/lists). null never appears here
# because defaults fill every field.
DEMO_BASKET = [
  {
    "name": "ANKER A2674 336 GaN 67W 急速充電器 2入組",
    "price": 1369.0,
    "currency": "TWD",
    "sku": "149699",
    "url": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/ANKER-A2674-336-GaN-67W-Charger-2-Pack/p/149699",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/ANKER-A2674-336-GaN-67W-Charger-2-Pack/p/149699"
  },
  {
    "name": "Soundcore AeroClip 開放式藍牙耳夾耳機",
    "price": 2599.0,
    "currency": "TWD",
    "sku": "161367",
    "url": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/Soundcore-AeroClip-Open-Ear-Clip-On-Earbuds/p/161367",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/Soundcore-AeroClip-Open-Ear-Clip-On-Earbuds/p/161367"
  },
  {
    "name": "iClever BTH18 炫光無線兒童耳機",
    "price": 1079.0,
    "currency": "TWD",
    "sku": "156974",
    "url": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/iClever-BTH18-Kids-Bluetooth-Wireless-Headphones/p/156974",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/iClever-BTH18-Kids-Bluetooth-Wireless-Headphones/p/156974"
  },
  {
    "name": "JBL Live 670NC 耳罩式降噪藍牙耳機",
    "price": 2399.0,
    "currency": "TWD",
    "sku": "153876",
    "url": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/JBL-Live-670NC-Over-ear-Noise-Cancelling-Bluetooth-Headphones/p/153876",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/JBL-Live-670NC-Over-ear-Noise-Cancelling-Bluetooth-Headphones/p/153876"
  },
  {
    "name": "Hawk 360° 旋轉升降螢幕架 附抽屜",
    "price": 839.0,
    "currency": "TWD",
    "sku": "162427",
    "url": "https://www.costco.com.tw/Digital-Mobile/Office-Equipment-Accessories/Paper-Shredders-Office-Equipment/Hawk-360-Rotating-Height-Adjustable-Monitor-Stand-with-Drawer/p/162427",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Office-Equipment-Accessories/Paper-Shredders-Office-Equipment/Hawk-360-Rotating-Height-Adjustable-Monitor-Stand-with-Drawer/p/162427"
  },
  {
    "name": "PQI 100W 數位顯示充電器",
    "price": 1379.0,
    "currency": "TWD",
    "sku": "161051",
    "url": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/PQI-100W-Digital-Display-Wall-Charger/p/161051",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/PQI-100W-Digital-Display-Wall-Charger/p/161051"
  },
  {
    "name": "Soodatek PD 65W 氮化鎵高速充電 USB-C 套裝",
    "price": 825.0,
    "currency": "TWD",
    "sku": "143371",
    "url": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/Soodatek-GaN-PD-65W-Charger-with-USB-C-Cable-Combo-Pack/p/143371",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/Soodatek-GaN-PD-65W-Charger-with-USB-C-Cable-Combo-Pack/p/143371"
  },
  {
    "name": "Acer Gaming USB-A to USB-C 1公尺 白 + USB-C to USB-C 1.2公尺 白...",
    "price": 599.0,
    "currency": "TWD",
    "sku": "153862",
    "url": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/Acer-Gaming-USB-A-to-USB-C-1-m-White-USB-C-to-USB-C-12-m-White-USB-C-to-USB-C-2-m-White-Silicone-Braided-Cable-3-Pack-Set/p/153862",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/Acer-Gaming-USB-A-to-USB-C-1-m-White-USB-C-to-USB-C-12-m-White-USB-C-to-USB-C-2-m-White-Silicone-Braided-Cable-3-Pack-Set/p/153862"
  },
  {
    "name": "JLab Epic Sport ANC 3 運動降噪真無線藍牙耳機",
    "price": 2899.0,
    "currency": "TWD",
    "sku": "153868",
    "url": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/Epic-Sport-ANC-3-True-Wireless-Earbuds/p/153868",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/Epic-Sport-ANC-3-True-Wireless-Earbuds/p/153868"
  },
  {
    "name": "Apple AirPods 5",
    "price": 4249.0,
    "currency": "TWD",
    "sku": "169089",
    "url": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/Apple-AirPods-5/p/169089",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/Apple-AirPods-5/p/169089"
  },
  {
    "name": "SteelSeries 賽睿 Qck Performance 滑鼠墊 XL-Control",
    "price": 1299.0,
    "currency": "TWD",
    "sku": "157689",
    "url": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Keyboards-Mice-Computer-Accessories/SteelSeries-Qck-Performance-Mouse-Pad-XL-Control/p/157689",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Keyboards-Mice-Computer-Accessories/SteelSeries-Qck-Performance-Mouse-Pad-XL-Control/p/157689"
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
    "name": "PowerA 任天堂官方授權 有線耳機 卡比 NSHS0299-01",
    "price": 979.0,
    "currency": "TWD",
    "sku": "158849",
    "url": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Video-Games-Consoles/PowerA-Officially-Licensed-Nintendo-Wired-Headphones-Kirby-NSHS0299-01/p/158849",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Video-Games-Consoles/PowerA-Officially-Licensed-Nintendo-Wired-Headphones-Kirby-NSHS0299-01/p/158849"
  },
  {
    "name": "HP 14吋筆記型電腦 EliteBook 6 G1q",
    "price": 34999.0,
    "currency": "TWD",
    "sku": "160448",
    "url": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Laptops/HP-14-inch-Laptop-EliteBook-6-G1q/p/160448",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Laptops/HP-14-inch-Laptop-EliteBook-6-G1q/p/160448"
  },
  {
    "name": "Flexispot 氣壓式升降邊桌",
    "price": 1599.0,
    "currency": "TWD",
    "sku": "149915",
    "url": "https://www.costco.com.tw/Furniture-Kitchen/Furniture/Computer-Desk-Chair-Sets/Flexispot-Adjustable-Side-Table/p/149915",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Furniture-Kitchen/Furniture/Computer-Desk-Chair-Sets/Flexispot-Adjustable-Side-Table/p/149915"
  },
  {
    "name": "BOSE Solo Soundbar 電視音響 II",
    "price": 8149.0,
    "currency": "TWD",
    "sku": "3062725",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/BOSE-Solo-Soundbar-TV-Speaker-II/p/3062725",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/BOSE-Solo-Soundbar-TV-Speaker-II/p/3062725"
  },
  {
    "name": "飛利浦 55吋 4K QLED Google TV 顯示器 55PQT8530/96",
    "price": 15799.0,
    "currency": "TWD",
    "sku": "153526",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Television/Philips-55-inch-4K-UHD-Smart-TV/p/153526",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Television/Philips-55-inch-4K-UHD-Smart-TV/p/153526"
  },
  {
    "name": "Honeywell 淨味空氣清淨機 HPA5350WTWV1",
    "price": 6999.0,
    "currency": "TWD",
    "sku": "157137",
    "url": "https://www.costco.com.tw/Televisions-Appliances/Air-Conditioners-Fans/Coolers-Humidifiers/Honeywell-Air-Purifier-AC1025D/p/157137",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/Air-Conditioners-Fans/Coolers-Humidifiers/Honeywell-Air-Purifier-AC1025D/p/157137"
  },
  {
    "name": "TCL 75吋 4K Mini LED Google TV 量子智能液晶顯示器 不含視訊盒 75C6K | Cos...",
    "price": 27799.0,
    "currency": "TWD",
    "sku": "153555",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/70-79-TVs/TCL-75-inch-4K-Mini-LED-Google-TV-Smart-Monitor-without-Tuner-Box-75C6K/p/153555",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/70-79-TVs/TCL-75-inch-4K-Mini-LED-Google-TV-Smart-Monitor-without-Tuner-Box-75C6K/p/153555"
  },
  {
    "name": "JBL BAR 2.1 DEEP BASS (MK2) 2.1聲道條型音箱",
    "price": 9699.0,
    "currency": "TWD",
    "sku": "154155",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/JBL-BAR-21-DEEP-BASS-MK2-Channel-Soundbar-With-Wireless-Subwoofer/p/154155",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/JBL-BAR-21-DEEP-BASS-MK2-Channel-Soundbar-With-Wireless-Subwoofer/p/154155"
  },
  {
    "name": "Denon 3.1.2 聲道 Dolby Atmos Soundbar 重低音組合 DHT-S517 | Cost...",
    "price": 14999.0,
    "currency": "TWD",
    "sku": "144030",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Denon-312-CH-Soundbar-with-Dolby-Atmos-and-Wireless-Subwoofer-DHT-S517/p/144030",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Denon-312-CH-Soundbar-with-Dolby-Atmos-and-Wireless-Subwoofer-DHT-S517/p/144030"
  },
  {
    "name": "Klipsch R-50PM 兩聲道主動式喇叭",
    "price": 14799.0,
    "currency": "TWD",
    "sku": "148980",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Klipsch-R-50Pm-Powered-Speakers-with-525-inch-Woofers/p/148980",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Klipsch-R-50Pm-Powered-Speakers-with-525-inch-Woofers/p/148980"
  },
  {
    "name": "Samsung 3.1聲道 兩件式家庭劇院含重低音 HW-S700D/ZW",
    "price": 9999.0,
    "currency": "TWD",
    "sku": "149115",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Samsung-31Ch-Ultra-Slim-Soundbar-HW-S700DZW/p/149115",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Samsung-31Ch-Ultra-Slim-Soundbar-HW-S700DZW/p/149115"
  },
  {
    "name": "Sony 3.1聲道 BRAVIA Theatre Bar 5 單件式喇叭搭配無線重低音揚聲器 HT-B500 |...",
    "price": 11949.0,
    "currency": "TWD",
    "sku": "162420",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Sony-31-Channel-BRAVIA-Theatre-Bar-5-Soundbar-with-Wireless-Subwoofer-HT-B500/p/162420",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Sony-31-Channel-BRAVIA-Theatre-Bar-5-Soundbar-with-Wireless-Subwoofer-HT-B500/p/162420"
  },
  {
    "name": "DeWALT 得偉 乾濕兩用吸塵器",
    "price": 3399.0,
    "currency": "TWD",
    "sku": "6677010",
    "url": "https://www.costco.com.tw/Televisions-Appliances/Small-Appliances/Vacuums-Floor-Care/DeWALT-DryWet-Vacuum/p/6677010",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/Small-Appliances/Vacuums-Floor-Care/DeWALT-DryWet-Vacuum/p/6677010"
  },
  {
    "name": "創維 75吋 4K QLED HSR120 AI卡拉OK 聯網液晶顯示器 75Q750GK",
    "price": 25999.0,
    "currency": "TWD",
    "sku": "153992",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/70-79-TVs/Skyworth-75-Inch-4K-QLED-HSR120-AI-Karaoke-Smart-Monitor-75Q750GK/p/153992",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/70-79-TVs/Skyworth-75-Inch-4K-QLED-HSR120-AI-Karaoke-Smart-Monitor-75Q750GK/p/153992"
  },
  {
    "name": "飛利浦 55吋 4K Google TV 顯示器 55PUH7630/96",
    "price": 13699.0,
    "currency": "TWD",
    "sku": "153519",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/Philips-55-inch-4K-Google-TV-Monitor-55PUH763096/p/153519",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/Philips-55-inch-4K-Google-TV-Monitor-55PUH763096/p/153519"
  },
  {
    "name": "Samsung 55吋 Mini LED 4K AI 量子智慧顯示器 UA55M1EHAXXZW | Costco...",
    "price": 18999.0,
    "currency": "TWD",
    "sku": "161520",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/Samsung-55-inch-Mini-LED-4K-AI-Smart-Monitor-UA55M1EHAXXZW/p/161520",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/Samsung-55-inch-Mini-LED-4K-AI-Smart-Monitor-UA55M1EHAXXZW/p/161520"
  },
  {
    "name": "東芝 Regza 55型 QLED144Hz 全陣列背光智慧顯示器 55Z670NT",
    "price": 18999.0,
    "currency": "TWD",
    "sku": "156638",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/Toshiba-Regza-55-inch-Full-Array-QLED-144Hz-Smart-Monitor-55Z670NT/p/156638",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/Toshiba-Regza-55-inch-Full-Array-QLED-144Hz-Smart-Monitor-55Z670NT/p/156638"
  },
  {
    "name": "TCL 55吋 4K Mini LED Google TV 量子智能液晶顯示器 不含視訊盒 55C6K | Cos...",
    "price": 19999.0,
    "currency": "TWD",
    "sku": "153539",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/TCL-55-inch-4K-Mini-LED-Google-TV-Smart-Monitor-without-Tuner-Box-55C6K/p/153539",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/TCL-55-inch-4K-Mini-LED-Google-TV-Smart-Monitor-without-Tuner-Box-55C6K/p/153539"
  }
]

__all__ = ["DEMO_BASKET"]
