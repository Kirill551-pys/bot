"""
Словарь алиасов команд для матчинга между The Odds API и model.pkl
"""

TEAM_ALIASES = {
    # ==================== EPL ====================
    "Man United": "Manchester United",
    "Man Utd": "Manchester United",
    "Man City": "Manchester City",
    "Manchester City": "Manchester City", 
    "Coventry City": "Coventry City",   
    "Hull City": "Hull City",    
    "Leicester City": "Leicester City",  
    "Stoke City": "Stoke City",     
    "Nott'm Forest": "Nottingham Forest",
    "Nottingham Forest": "Nottingham Forest",
    "Brighton": "Brighton",
    "Brighton and Hove Albion": "Brighton",
    "Wolves": "Wolverhampton Wanderers",
    "Wolverhampton": "Wolverhampton Wanderers",
    "West Ham": "West Ham United",
    "West Ham United": "West Ham United",
    "Newcastle": "Newcastle United",
    "Newcastle United": "Newcastle United",
    "Sheffield Utd": "Sheffield United",
    "Sheffield United": "Sheffield United",
    "Tottenham": "Tottenham Hotspur",
    "Tottenham Hotspur": "Tottenham Hotspur",
    
    # ==================== LaLiga ====================
    "Athletic Club": "Athletic Bilbao",
    "Athletic Bilbao": "Athletic Bilbao",
    "Atletico Madrid": "Atlético Madrid",
    "Atlético Madrid": "Atlético Madrid",
    "Atletico de Madrid": "Atlético Madrid",
    "Real Betis": "Betis",
    "Betis": "Betis",
    "Real Sociedad": "Real Sociedad",
    "Celta Vigo": "Celta de Vigo",
    "Celta de Vigo": "Celta de Vigo",
    "Real Valladolid": "Valladolid",
    "Rayo Vallecano": "Rayo Vallecano",
    
    # ==================== Bundesliga ====================
    "Eintracht Frankfurt": "Eintracht Frankfurt",
    "Bayer Leverkusen": "Bayer 04 Leverkusen",
    "Bayer 04 Leverkusen": "Bayer 04 Leverkusen",
    "Leverkusen": "Bayer 04 Leverkusen",
    "RB Leipzig": "RasenBallsport Leipzig",
    "RasenBallsport Leipzig": "RasenBallsport Leipzig",
    "Borussia Dortmund": "Borussia Dortmund",
    "Borussia M.Gladbach": "Borussia Mönchengladbach",
    "Borussia Monchengladbach": "Borussia Mönchengladbach",
    "Borussia M'gladbach": "Borussia Mönchengladbach",
    "FSV Mainz 05": "Mainz",
    "Mainz 05": "Mainz",
    "Mainz": "Mainz",
    "Hoffenheim": "TSG Hoffenheim",
    "TSG Hoffenheim": "TSG Hoffenheim",
    
    # ==================== Serie A ====================
    "AC Milan": "Milan",
    "Milan": "Milan",
    "Inter": "Inter",
    "Inter Milan": "Inter",
    "Napoli": "Napoli",
    "Juventus": "Juventus",
    "AS Roma": "Roma",
    "Roma": "Roma",
    "Lazio": "Lazio",
    "Hellas Verona": "Verona",
    "Verona": "Verona",
    "SPAL 2013": "Spal",
    
    # ==================== Ligue 1 ====================
    "Paris SG": "Paris Saint Germain",
    "Paris Saint-Germain": "Paris Saint Germain",
    "Olympique Marseille": "Marseille",
    "Marseille": "Marseille",
    "Olympique Lyonnais": "Lyon",
    "Lyon": "Lyon",
    "AS Monaco": "Monaco",
    "Monaco": "Monaco",
    
    # ==================== RPL ====================
    "Zenit": "Zenit",
    "Zenit St Petersburg": "Zenit",
    "Zenit Saint Petersburg": "Zenit",
    "CSKA Moscow": "CSKA Moscow",
    "CSKA Moskva": "CSKA Moscow",
    "Spartak Moscow": "Spartak Moscow",
    "Spartak Moskva": "Spartak Moscow",
    "Lokomotiv Moscow": "Lokomotiv Moscow",
    "Lokomotiv Moskva": "Lokomotiv Moscow",
    "Dynamo Moscow": "Dynamo Moscow",
    "Dinamo Moscow": "Dynamo Moscow",
    "FC Krasnodar": "Krasnodar",
    "Krasnodar": "Krasnodar",
    
    # ==================== Eredivisie ====================
    "Ajax": "Ajax",
    "PSV": "PSV Eindhoven",
    "PSV Eindhoven": "PSV Eindhoven",
    "FC Twente Enschede": "Twente",
    "FC Twente": "Twente",
    "Twente": "Twente",
    "Feyenoord": "Feyenoord Rotterdam",
    "Feyenoord Rotterdam": "Feyenoord Rotterdam",
    
    # ==================== Turkey ====================
    "Galatasaray": "Galatasaray",
    "Fenerbahce": "Fenerbahce",
    "Fenerbahçe": "Fenerbahce",
    "Besiktas": "Besiktas",
    "Beşiktaş": "Besiktas",
    "Trabzonspor": "Trabzonspor",
    
    # ==================== Greece ====================
    "Olympiacos": "Olympiakos",
    "Olympiakos": "Olympiakos",
    "Panathinaikos": "Panathinaikos",
    "AEK Athens": "AEK Athens",
    
    # ==================== Portugal ====================
    "Benfica": "Benfica",
    "Sporting CP": "Sporting Lisbon",
    "Porto": "Porto",
    "FC Porto": "Porto",
}


def normalize_team_name(name: str) -> str:
    """Нормализует название команды через словарь алиасов"""
    if not name:
        return name
    
    # Точное совпадение
    if name in TEAM_ALIASES:
        return TEAM_ALIASES[name]
    
    # Нечувствительный к регистру поиск
    name_lower = name.lower()
    for alias, full_name in TEAM_ALIASES.items():
        if alias.lower() == name_lower:
            return full_name
    
    # Убираем префиксы "FC ", "SC ", "AC ", "AS " для повышения шансов
    for prefix in ['FC ', 'SC ', 'AC ', 'AS ', 'CF ', 'CD ']:
        if name.startswith(prefix):
            short_name = name[len(prefix):]
            if short_name in TEAM_ALIASES:
                return TEAM_ALIASES[short_name]
    
    return name