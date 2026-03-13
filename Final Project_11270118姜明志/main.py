from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from poker_hand import card_power, card_type  # 引入 牌力、牌型
from bot_token import token  # 引入 token
import random

# 定義花色、點數變數
ply = ['電腦 1', '電腦 2', '電腦 3', '玩家 (我)']
weight = list('23456789TJQKA')
flower = ['♠', '♥', '♦', '♣']

# 定義遊戲變數
round_number = 0            # 遊戲局數
round_stage = 0             # 遊戲階段
community_cards = []        # 公共牌
shuffled_deck = []          # 洗牌的牌堆
ply_money = [100]*4         # 資金
ply_status = [None]*4       # 狀態
ply_bet = [0]*4             # 下注
ply_hand = [[]]*4           # 玩家手牌

# 輸出 poker
def format_cards(cards):
    return " ".join(cards)

# 產生 poker
def generate_deck():
    return [rank + suit for suit in flower for rank in weight]

# 發牌
def deal_cards():
    global ply_hand, shuffled_deck
    for _ in range(2):
        for i in range(4):
            ply_hand[i].append(shuffled_deck.pop())

# 顯示公共牌 + 玩家狀態
def board():
    info = f"第 {round_number} 局 | 階段：{['待機','翻牌前','翻牌','轉牌','河牌'][round_stage]}\n\n"
    info += f"公共牌：{format_cards(community_cards)}\n\n"
    for i in range(3):
        info += f"{ply[i]}：{ply_status[i]} | 下注：{ply_bet[i]} | 剩餘金額：{ply_money[i]}\n"
    info += f"\n你的手牌：{format_cards(ply_hand[3])} | 狀態：{ply_status[3]} | 下注：{ply_bet[3]} | 剩餘金額：{ply_money[3]}"
    return info

# 玩家操作選項
def action_buttons():
    buttons = []
    if round_number >= 5:
        buttons.append([InlineKeyboardButton('全押', callback_data='all')])
    buttons.append([InlineKeyboardButton('押注 1 元', callback_data='bet')])
    buttons.append([InlineKeyboardButton('棄牌', callback_data='drop')])
    return InlineKeyboardMarkup(buttons)

# 跳過
def skip_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('跳過', callback_data='skip')]
    ])

# 新輪遊戲
async def deal(update, context):
    global round_number, shuffled_deck, ply_hand, community_cards, ply_status, ply_bet, round_stage
    if round_stage != 0:
        return
    round_number += 1
    round_stage = 1
    shuffled_deck = generate_deck()
    random.shuffle(shuffled_deck)
    ply_hand = [[] for _ in range(4)]
    community_cards.clear()
    ply_bet[:] = [0] * 4
    ply_status[:] = [''] * 4
    deal_cards()
    await run_stage(update)

# 加入公共牌、執行電腦、等待玩家
async def run_stage(update_or_query):
    global round_stage, community_cards
    if round_stage == 2:
        community_cards.extend([shuffled_deck.pop() for _ in range(3)])
    elif round_stage in [3, 4]:
        community_cards.append(shuffled_deck.pop())
    await cpu_actions()
    send = update_or_query.message.reply_text if isinstance(update_or_query, Update) else update_or_query.edit_message_text
    if ply_status[3] in ['棄牌', '全押']:
        await send(board(), reply_markup=skip_button())
    else:
        await send(board(), reply_markup=action_buttons())

# 玩家回應
async def action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global round_stage
    query = update.callback_query
    await query.answer()

    if query.data == 'skip':
        round_stage += 1
        if round_stage <= 4:
            await run_stage(query)
        else:
            await end_round(query)
        return

    if query.data == 'all' and round_number < 5:
        await query.edit_message_text(
            board() + "\n\n第 5 局之後才能全押！",
            reply_markup=action_buttons()
        )
        return

    if query.data == 'all':
        ply_bet[3] = ply_money[3]
        ply_status[3] = '全押'
        ply_money[3] = 0
    elif query.data == 'bet':
        if ply_money[3] > 0:
            ply_bet[3] += 1
            ply_money[3] -= 1
            ply_status[3] = '押注'
        else:
            ply_status[3] = '過牌'
    elif query.data == 'drop':
        ply_status[3] = '棄牌'

    round_stage += 1
    if round_stage <= 4:
        await run_stage(query)
    else:
        await end_round(query)

# 電腦策略
async def cpu_actions():
    for i in range(3):
        if ply_status[i] in ['棄牌', '全押']:
            continue
        power = card_power(ply_hand[i] + community_cards)

        if i == 0:
            if ply_money[i] > 0:
                ply_money[i] -= 1
                ply_bet[i] += 1
                ply_status[i] = '押注'
        elif i == 1:
            if round_stage == 1 or (round_stage == 2 and power != 9):
                ply_money[i] -= 1
                ply_bet[i] += 1
                ply_status[i] = '押注'
            elif round_stage == 2 and power == 9:
                ply_status[i] = '棄牌'
            elif round_stage in [3, 4]:
                if power <= 3:
                    ply_bet[i] += ply_money[i]
                    ply_money[i] = 0
                    ply_status[i] = '全押'
                else:
                    ply_money[i] -= 1
                    ply_bet[i] += 1
                    ply_status[i] = '押注'
        elif i == 2:
            if round_stage == 1:
                ply_money[i] -= 1
                ply_bet[i] += 1
                ply_status[i] = '押注'
            elif round_stage == 2 and power >= 7:
                ply_status[i] = '棄牌'

# 結算遊戲
async def end_round(query):
    global round_stage
    pot = sum(ply_bet)
    results = []

    for i in range(4):
        full_hand = ply_hand[i] + community_cards
        power = card_power(full_hand)
        results.append((power, i))

    results.sort()
    best_power = results[0][0]
    winners = [i for i in range(4) if card_power(ply_hand[i] + community_cards) == best_power]

    msg = f"第 {round_number} 局結果：\n\n公共牌：{format_cards(community_cards)}\n\n"
    for power, i in results:
        full_type = card_type(ply_hand[i] + community_cards)
        msg += f"{ply[i]}：{format_cards(ply_hand[i])} [{full_type}] | 下注：{ply_bet[i]} | 剩餘：{ply_money[i]}\n"

    msg += f"\n總獎金池：{pot}\n獲勝者：{', '.join([ply[w] for w in winners])}\n"

    if any(m > 250 or m <= 0 for m in ply_money):
        msg += "\n遊戲結束！輸入 /start 重新開始。"
        round_stage = 0
    else:
        msg += "\n輸入 /deal 開始下一局。"
        round_stage = 0

    prize = pot // len(winners)
    for i in winners:
        ply_money[i] += prize

    await query.edit_message_text(msg)

# 開始遊戲
async def start(update, context):
    global ply_money, ply_status, ply_bet, ply_hand, community_cards, shuffled_deck, round_number, round_stage
    ply_money = [100]*4
    ply_status = [None]*4
    ply_bet = [0]*4
    ply_hand = [[]]*4
    community_cards = []
    shuffled_deck = []
    round_number = 0
    round_stage = 0
    await update.message.reply_text("遊戲開始！\n每位玩家起始有 $100。\n輸入 /deal 發牌開始新一局。")

def main():
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("deal", deal))
    app.add_handler(CallbackQueryHandler(action))
    app.run_polling()

if __name__ == "__main__":
    main()
