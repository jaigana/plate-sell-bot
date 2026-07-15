from aiogram.fsm.state import State, StatesGroup


class UserInput(StatesGroup):
    search = State()
    mint_plate = State()
    sale_price = State()
    auction_price = State()
    auction_duration = State()
    bid_amount = State()
    topup_amount = State()


class AdminInput(StatesGroup):
    user_lookup = State()
    block_reason = State()
    balance_adjustment = State()
    plate_lookup = State()
    transfer_target = State()
    auction_lookup = State()
    setting_value = State()
    refund_charge_id = State()
    card_edit = State()
