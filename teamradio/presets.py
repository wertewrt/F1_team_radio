"""Presets traced from the user's reference screenshots, not a live grid roster."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'assets'
TEAMS = {
    'mercedes': {'name':'Mercedes · 梅赛德斯','color':'#26E7C8','logo_variant':'white'},
    'ferrari': {'name':'Ferrari · 法拉利','color':'#ED123F','logo_variant':'color'},
    'mclaren': {'name':'McLaren · 迈凯伦','color':'#FF8A00','logo_variant':'white'},
    'red_bull': {'name':'Red Bull · 红牛','color':'#3876CD','logo_variant':'color'},
    'racing_bulls': {'name':'Racing Bulls · 红牛二队','color':'#80A2FF','logo_variant':'white'},
    'alpine': {'name':'Alpine · 阿尔派','color':'#00A7DF','logo_variant':'white'},
    'haas': {'name':'Haas · 哈斯','color':'#E8E9EB','logo_variant':'color'},
    'audi': {'name':'Audi · 奥迪','color':'#FF3C14','logo_variant':'white'},
    'williams': {'name':'Williams · 威廉姆斯','color':'#246DCB','logo_variant':'white'},
    'aston_martin': {'name':'Aston Martin · 阿斯顿马丁','color':'#239D7D','logo_variant':'white'},
    'cadillac': {'name':'Cadillac · 凯迪拉克','color':'#B8BAC0','logo_variant':'white'},
}
DRIVERS = {
    'albon': {'name':'ALBON','number':'23','team':'williams'},
    'sainz': {'name':'SAINZ','number':'55','team':'williams'},
    'russell': {'name':'RUSSELL','number':'63','team':'mercedes'},
    'antonelli': {'name':'ANTONELLI','number':'12','team':'mercedes'},
    'leclerc': {'name':'LECLERC','number':'16','team':'ferrari'},
    'hamilton': {'name':'HAMILTON','number':'44','team':'ferrari'},
    'norris': {'name':'NORRIS','number':'1','team':'mclaren'},
    'piastri': {'name':'PIASTRI','number':'81','team':'mclaren'},
    'verstappen': {'name':'VERSTAPPEN','number':'3','team':'red_bull'},
    'hadjar': {'name':'HADJAR','number':'6','team':'red_bull'},
    'lawson': {'name':'LAWSON','number':'30','team':'racing_bulls'},
    'lindblad': {'name':'LINDBLAD','number':'41','team':'racing_bulls'},
    'tsunoda': {'name':'TSUNODA','number':'22','team':'racing_bulls'},
    'gasly': {'name':'GASLY','number':'10','team':'alpine'},
    'colapinto': {'name':'COLAPINTO','number':'43','team':'alpine'},
    'ocon': {'name':'OCON','number':'31','team':'haas'},
    'bearman': {'name':'BEARMAN','number':'87','team':'haas'},
    'hulkenberg': {'name':'HULKENBERG','number':'27','team':'audi'},
    'bortoleto': {'name':'BORTOLETO','number':'5','team':'audi'},
    'alonso': {'name':'ALONSO','number':'14','team':'aston_martin'},
    'stroll': {'name':'STROLL','number':'18','team':'aston_martin'},
    'perez': {'name':'PEREZ','number':'11','team':'cadillac'},
    'bottas': {'name':'BOTTAS','number':'77','team':'cadillac'},
}

def logo_path(team, variant=None):
    return ASSETS / 'logos' / f"{team}_{variant or TEAMS[team]['logo_variant']}.png"
