"""Offline snapshot of Costco 3C + 家電 PDP prices.

Refreshed 2026-11-28 via BFS crawl of Costco PDP "相關推薦" links
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
    "name": "Tresanti 電動升降桌",
    "price": 5999.0,
    "currency": "TWD",
    "sku": "1646074",
    "url": "https://www.costco.com.tw/Furniture-Kitchen/Furniture/Computer-Desk-Chair-Sets/Tresanti-Adjustable-Desk/p/1646074",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Furniture-Kitchen/Furniture/Computer-Desk-Chair-Sets/Tresanti-Adjustable-Desk/p/1646074"
  },
  {
    "name": "MMOMENT 512GB 磁性外接可攜式固態硬碟 SSD",
    "price": 3059.0,
    "currency": "TWD",
    "sku": "159542",
    "url": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Data-Storage/MMOMENT-512GB-Magnetic-External-Portable-SSD/p/159542",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Data-Storage/MMOMENT-512GB-Magnetic-External-Portable-SSD/p/159542"
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
    "name": "Soodatek GaN PD140W 氮化鎵急速充電 USB-C 套裝",
    "price": 1479.0,
    "currency": "TWD",
    "sku": "157488",
    "url": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/Soodatek-GaN-PD140W-Fast-Charger-with-USB-C-Cable-Combo-pack/p/157488",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/Soodatek-GaN-PD140W-Fast-Charger-with-USB-C-Cable-Combo-pack/p/157488"
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
    "name": "Acer Gaming USB-A to USB-C 1公尺 白 + USB-C to USB-C 1.2公尺 白...",
    "price": 599.0,
    "currency": "TWD",
    "sku": "153862",
    "url": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/Acer-Gaming-USB-A-to-USB-C-1-m-White-USB-C-to-USB-C-12-m-White-USB-C-to-USB-C-2-m-White-Silicone-Braided-Cable-3-Pack-Set/p/153862",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/Acer-Gaming-USB-A-to-USB-C-1-m-White-USB-C-to-USB-C-12-m-White-USB-C-to-USB-C-2-m-White-Silicone-Braided-Cable-3-Pack-Set/p/153862"
  },
  {
    "name": "PQI 35W 雙孔氮化鎵 PD/QC3.0 快速充電器 附二合一 USB-C to USB-C/Lightnin...",
    "price": 959.0,
    "currency": "TWD",
    "sku": "139339",
    "url": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/PQI-35W-Dual-Port-GaN-PDQC30-Fast-Charger-with-2-in-1-USB-C-to-USB-C-and-Lightning-Cable-120-cm/p/139339",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Mobile-Tablets/Mobile-Tablets-Accessories/PQI-35W-Dual-Port-GaN-PDQC30-Fast-Charger-with-2-in-1-USB-C-to-USB-C-and-Lightning-Cable-120-cm/p/139339"
  },
  {
    "name": "Apple 60W USB-C 充電連接線 (1 公尺)",
    "price": 539.0,
    "currency": "TWD",
    "sku": "147653",
    "url": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Keyboards-Mice-Computer-Accessories/Apple-60W-USB-C-Charge-Cable-1-m/p/147653",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Laptops-Computers/Keyboards-Mice-Computer-Accessories/Apple-60W-USB-C-Charge-Cable-1-m/p/147653"
  },
  {
    "name": "Klipsch GIG XL 藍牙派對音響 含Fiesta有線麥克風",
    "price": 4389.0,
    "currency": "TWD",
    "sku": "162860",
    "url": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Bluetooth-Speakers-Landline-Phones/Klipsch-GIG-XL-Bluetooth-Party-Speaker-with-Fiesta-Wired-Microphone/p/162860",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Bluetooth-Speakers-Landline-Phones/Klipsch-GIG-XL-Bluetooth-Party-Speaker-with-Fiesta-Wired-Microphone/p/162860"
  },
  {
    "name": "墨覺 專業游泳骨傳導耳機",
    "price": 2999.0,
    "currency": "TWD",
    "sku": "163848",
    "url": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/Mojawa-Bone-Conduction-Swimming-Headphones/p/163848",
    "tag": "3C",
    "category_path": "https://www.costco.com.tw/Digital-Mobile/Wearables-Audio/Headphones-Audio-Devices/Mojawa-Bone-Conduction-Swimming-Headphones/p/163848"
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
    "price": 9099.0,
    "currency": "TWD",
    "sku": "157137",
    "url": "https://www.costco.com.tw/Televisions-Appliances/Air-Conditioners-Fans/Coolers-Humidifiers/Honeywell-Air-Purifier-AC1025D/p/157137",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/Air-Conditioners-Fans/Coolers-Humidifiers/Honeywell-Air-Purifier-AC1025D/p/157137"
  },
  {
    "name": "TCL 75吋 4K Mini LED Google TV 量子智能液晶顯示器 不含視訊盒 75C6K | Cos...",
    "price": 34799.0,
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
    "name": "Jamo Cinema 3 聲霸+重低音組合",
    "price": 10999.0,
    "currency": "TWD",
    "sku": "163482",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Jamo-Cinema-3-Soundbar-with-Wireless-Subwoofer/p/163482",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Jamo-Cinema-3-Soundbar-with-Wireless-Subwoofer/p/163482"
  },
  {
    "name": "Recolte 食物調理機 RCP-3 (有線版)",
    "price": 1539.0,
    "currency": "TWD",
    "sku": "162967",
    "url": "https://www.costco.com.tw/Televisions-Appliances/Kitchen-Appliances/Coffee-Machines-Blenders-Juicers/Recolte-Food-Chopper-RCP-3/p/162967",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/Kitchen-Appliances/Coffee-Machines-Blenders-Juicers/Recolte-Food-Chopper-RCP-3/p/162967"
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
    "name": "Klipsch Flexus 無線聲霸 Core 100",
    "price": 9999.0,
    "currency": "TWD",
    "sku": "148022",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Klipsch-Flexus-Soundbar-Core-100/p/148022",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Klipsch-Flexus-Soundbar-Core-100/p/148022"
  },
  {
    "name": "飛利浦 2.1 聲道 無線重低音杜比全景聲聲霸 TAB6309",
    "price": 7599.0,
    "currency": "TWD",
    "sku": "147918",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Philips-21-CH-Soundbar-TAB6309/p/147918",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/Philips-21-CH-Soundbar-TAB6309/p/147918"
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
    "name": "TCL 65吋 4K Mini LED Google TV 量子智能液晶顯示器 不含視訊盒 65C6K | Cos...",
    "price": 24989.0,
    "currency": "TWD",
    "sku": "153537",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/60-69-TVs/TCL-65-inch-4K-Mini-LED-Google-TV-Smart-Monitor-without-Tuner-Box-65C6K/p/153537",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/60-69-TVs/TCL-65-inch-4K-Mini-LED-Google-TV-Smart-Monitor-without-Tuner-Box-65C6K/p/153537"
  },
  {
    "name": "飛利浦 55吋 4K Google TV 顯示器 55PUH7630/96",
    "price": 13699.0,
    "currency": "TWD",
    "sku": "153519",
    "url": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/Philips-55-inch-4K-Google-TV-Monitor-55PUH763096/p/153519",
    "tag": "家電",
    "category_path": "https://www.costco.com.tw/Televisions-Appliances/TV-Home-Entertainment/Televisions-TV-Accessories/50-59-TVs/Philips-55-inch-4K-Google-TV-Monitor-55PUH763096/p/153519"
  }
]

__all__ = ["DEMO_BASKET"]
