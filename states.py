from aiogram.fsm.state import State, StatesGroup

class MatchPrediction(StatesGroup):
    choosing_league = State()
    selecting_home_team = State()
    selecting_away_team = State()
    waiting_for_manual_input = State()