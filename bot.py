import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import unicodedata
import re
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TOKEN = os.environ.get("DISCORD_TOKEN")
DB_FILE = "games.json"
ITEMS_PER_PAGE = 8

# ─── DATABASE ─────────────────────────────────────────────────────────────────
def load_db():
    if not os.path.exists(DB_FILE):
        save_db({"proposed": [], "played": []})
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def normalize(name: str) -> str:
    """Normalize game name for comparison (ignore accents, case, spaces)"""
    name = name.lower().strip()
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = re.sub(r"[^a-z0-9]", "", name)
    return name

def find_game(db, name: str):
    norm = normalize(name)
    for g in db["proposed"]:
        if normalize(g["name"]) == norm:
            return ("proposed", g)
    for g in db["played"]:
        if normalize(g["name"]) == norm:
            return ("played", g)
    return (None, None)

# ─── BOT SETUP ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ─── VIEWS ────────────────────────────────────────────────────────────────────
class VoteView(discord.ui.View):
    def __init__(self, game_name: str):
        super().__init__(timeout=None)
        self.game_name = game_name

    @discord.ui.button(label="0", emoji="👍", style=discord.ButtonStyle.success, custom_id="vote_up")
    async def vote_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_db()
        _, game = find_game(db, self.game_name)
        if not game:
            await interaction.response.send_message("❌ Jeu introuvable.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        if uid in game.get("votes_up", []):
            await interaction.response.send_message("T'as déjà voté 👍 pour ce jeu !", ephemeral=True)
            return
        game.setdefault("votes_up", [])
        game.setdefault("votes_down", [])
        if uid in game["votes_down"]:
            game["votes_down"].remove(uid)
        game["votes_up"].append(uid)
        save_db(db)
        # Update button labels
        self.children[0].label = str(len(game["votes_up"]))
        self.children[1].label = str(len(game["votes_down"]))
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="0", emoji="👎", style=discord.ButtonStyle.danger, custom_id="vote_down")
    async def vote_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_db()
        _, game = find_game(db, self.game_name)
        if not game:
            await interaction.response.send_message("❌ Jeu introuvable.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        if uid in game.get("votes_down", []):
            await interaction.response.send_message("T'as déjà voté 👎 pour ce jeu !", ephemeral=True)
            return
        game.setdefault("votes_up", [])
        game.setdefault("votes_down", [])
        if uid in game["votes_up"]:
            game["votes_up"].remove(uid)
        game["votes_down"].append(uid)
        save_db(db)
        self.children[0].label = str(len(game["votes_up"]))
        self.children[1].label = str(len(game["votes_down"]))
        await interaction.response.edit_message(view=self)


class ListeView(discord.ui.View):
    def __init__(self, pages: list, current: int = 0):
        super().__init__(timeout=60)
        self.pages = pages
        self.current = current
        self._update_buttons()

    def _update_buttons(self):
        self.children[0].disabled = self.current == 0
        self.children[1].disabled = self.current >= len(self.pages) - 1

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)


# ─── COMMANDS ─────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot connecté : {bot.user} | Commandes sync OK")


@bot.tree.command(name="propose", description="📬 Proposer un jeu")
@app_commands.describe(jeu="Nom du jeu à proposer")
async def propose(interaction: discord.Interaction, jeu: str):
    db = load_db()
    status, existing = find_game(db, jeu)

    if status == "played":
        embed = discord.Embed(
            title="❌ Déjà joué !",
            description=f"**{existing['name']}** a déjà été joué. Propose autre chose !",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if status == "proposed":
        embed = discord.Embed(
            title="⚠️ Déjà proposé !",
            description=f"**{existing['name']}** est déjà dans la liste des propositions.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Nouveau jeu
    game = {
        "name": jeu.strip(),
        "proposed_by": interaction.user.display_name,
        "proposed_by_id": str(interaction.user.id),
        "date": datetime.now().strftime("%d/%m/%Y"),
        "votes_up": [],
        "votes_down": []
    }
    db["proposed"].append(game)
    save_db(db)

    embed = discord.Embed(
        title="🎮 Nouveau jeu proposé !",
        description=f"**{jeu.strip()}**",
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Proposé par {interaction.user.display_name} • {game['date']}")

    view = VoteView(jeu.strip())
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="joue", description="✅ Marquer un jeu comme joué")
@app_commands.describe(jeu="Nom du jeu que tu as joué")
async def joue(interaction: discord.Interaction, jeu: str):
    db = load_db()
    status, existing = find_game(db, jeu)

    if status == "played":
        embed = discord.Embed(
            title="✅ Déjà marqué joué !",
            description=f"**{existing['name']}** est déjà dans ta liste de jeux joués.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if status == "proposed":
        db["proposed"].remove(existing)
        existing["played_date"] = datetime.now().strftime("%d/%m/%Y")
        db["played"].append(existing)
        save_db(db)
        embed = discord.Embed(
            title="🏆 Jeu marqué comme joué !",
            description=f"**{existing['name']}** a été déplacé dans la liste des jeux joués.",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Marqué par {interaction.user.display_name} • {existing['played_date']}")
        await interaction.response.send_message(embed=embed)
        return

    # Pas dans la liste, on l'ajoute directement en joué
    game = {
        "name": jeu.strip(),
        "proposed_by": "—",
        "date": "—",
        "played_date": datetime.now().strftime("%d/%m/%Y"),
        "votes_up": [],
        "votes_down": []
    }
    db["played"].append(game)
    save_db(db)
    embed = discord.Embed(
        title="🏆 Jeu ajouté aux joués !",
        description=f"**{jeu.strip()}** ajouté directement à ta liste de jeux joués.",
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Marqué par {interaction.user.display_name} • {game['played_date']}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="liste", description="📋 Voir la liste des jeux proposés et joués")
@app_commands.describe(filtre="proposed = propositions | joue = joués | tout = les deux")
@app_commands.choices(filtre=[
    app_commands.Choice(name="Propositions", value="proposed"),
    app_commands.Choice(name="Joués", value="joue"),
    app_commands.Choice(name="Tout", value="tout"),
])
async def liste(interaction: discord.Interaction, filtre: str = "tout"):
    db = load_db()
    pages = []

    def make_pages(items, title, emoji, color):
        if not items:
            return
        chunks = [items[i:i+ITEMS_PER_PAGE] for i in range(0, len(items), ITEMS_PER_PAGE)]
        for idx, chunk in enumerate(chunks):
            embed = discord.Embed(title=f"{emoji} {title}", color=color)
            for g in chunk:
                votes = f"👍 {len(g.get('votes_up', []))}  👎 {len(g.get('votes_down', []))}"
                val = f"Proposé par **{g['proposed_by']}** le {g['date']}\n{votes}"
                if "played_date" in g:
                    val += f"\n✅ Joué le {g['played_date']}"
                embed.add_field(name=f"🎮 {g['name']}", value=val, inline=False)
            embed.set_footer(text=f"Page {idx+1}/{len(chunks)}")
            pages.append(embed)

    if filtre in ("proposed", "tout"):
        make_pages(db["proposed"], "Jeux proposés", "📬", discord.Color.blurple())
    if filtre in ("joue", "tout"):
        make_pages(db["played"], "Jeux joués", "🏆", discord.Color.gold())

    if not pages:
        await interaction.response.send_message("📭 Aucun jeu dans cette liste pour l'instant !", ephemeral=True)
        return

    view = ListeView(pages) if len(pages) > 1 else None
    await interaction.response.send_message(embed=pages[0], view=view)


@bot.tree.command(name="supprimer", description="🗑️ Supprimer une proposition (admin)")
@app_commands.describe(jeu="Nom du jeu à supprimer")
@app_commands.checks.has_permissions(manage_messages=True)
async def supprimer(interaction: discord.Interaction, jeu: str):
    db = load_db()
    status, existing = find_game(db, jeu)
    if not existing:
        await interaction.response.send_message(f"❌ **{jeu}** introuvable dans la liste.", ephemeral=True)
        return
    if status == "proposed":
        db["proposed"].remove(existing)
    else:
        db["played"].remove(existing)
    save_db(db)
    await interaction.response.send_message(f"🗑️ **{existing['name']}** supprimé de la liste.", ephemeral=True)


# ─── RUN ──────────────────────────────────────────────────────────────────────
bot.run(TOKEN)
