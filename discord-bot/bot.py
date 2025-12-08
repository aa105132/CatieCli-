"""
Catiecli Discord Bot - 用户注册与管理
通过 Discord 用户 ID 绑定账号，一人一号
"""
import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

# 配置
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5001")  # 内部调用
API_PUBLIC_URL = os.getenv("API_PUBLIC_URL", API_BASE_URL)  # 显示给用户
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0"))  # 管理员角色 ID

# Bot 设置
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


class RegisterModal(discord.ui.Modal, title="🐱 注册 Catiecli"):
    """注册表单"""
    username = discord.ui.TextInput(
        label="用户名 (3-20位，仅限数字和小写字母)",
        placeholder="例如: mygcliuser123",
        min_length=3,
        max_length=20,
        required=True
    )
    password = discord.ui.TextInput(
        label="密码 (6位以上)",
        placeholder="请设置一个安全的密码",
        min_length=6,
        max_length=50,
        required=True,
        style=discord.TextStyle.short
    )
    confirm_password = discord.ui.TextInput(
        label="确认密码",
        placeholder="请再次输入您的密码",
        min_length=6,
        max_length=50,
        required=True,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        # 验证密码
        if str(self.password) != str(self.confirm_password):
            await interaction.response.send_message("❌ 两次输入的密码不一致！", ephemeral=True)
            return
        
        # 验证用户名格式
        username = str(self.username).lower()
        if not username.isalnum():
            await interaction.response.send_message("❌ 用户名只能包含字母和数字！", ephemeral=True)
            return
        
        # 调用 API 注册
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{API_BASE_URL}/api/auth/register-discord",
                    json={
                        "username": username,
                        "password": str(self.password),
                        "discord_id": str(interaction.user.id),
                        "discord_name": str(interaction.user)
                    }
                ) as resp:
                    data = await resp.json()
                    
                    if resp.status == 200:
                        embed = discord.Embed(
                            title="🎉 注册成功！",
                            description=f"欢迎加入 Catiecli！",
                            color=discord.Color.green()
                        )
                        embed.add_field(name="用户名", value=username, inline=True)
                        embed.add_field(name="API Key", value=f"```{data.get('api_key', 'N/A')}```", inline=False)
                        embed.add_field(
                            name="使用方法",
                            value=f"API 地址: `{API_PUBLIC_URL}`\n"
                                  f"💡 直接填域名即可，无需添加 /v1\n"
                                  f"在请求头添加: `Authorization: Bearer YOUR_API_KEY`",
                            inline=False
                        )
                        embed.set_footer(text="请妥善保管您的 API Key")
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                    else:
                        error_msg = data.get("detail", "注册失败")
                        await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 服务器连接失败: {str(e)}", ephemeral=True)


class RegisterButton(discord.ui.View):
    """注册按钮"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 注册账号", style=discord.ButtonStyle.primary, custom_id="register_btn")
    async def register(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 检查是否已注册
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(
                    f"{API_BASE_URL}/api/auth/check-discord/{interaction.user.id}"
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("exists"):
                            embed = discord.Embed(
                                title="ℹ️ 您已注册",
                                description=f"您的账号: **{data.get('username')}**\n\n使用 `/key` 查看密钥\n使用 `/resetkey` 重新生成密钥",
                                color=discord.Color.blue()
                            )
                            embed.add_field(name="API Key", value=f"```{data.get('api_key', '请使用 /key 命令获取')}```", inline=False)
                            await interaction.response.send_message(embed=embed, ephemeral=True)
                            return
                        else:
                            # 未注册，显示注册表单
                            await interaction.response.send_modal(RegisterModal())
                            return
                    else:
                        await interaction.response.send_message("❌ 服务器繁忙，请稍后再试", ephemeral=True)
                        return
        except Exception as e:
            print(f"[RegisterButton] 检查注册状态失败: {e}")
            await interaction.response.send_message(f"❌ 无法连接服务器，请稍后再试", ephemeral=True)
            return


@bot.event
async def on_ready():
    print(f"🐱 Catiecli Bot 已启动: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ 已同步 {len(synced)} 个斜杠命令")
    except Exception as e:
        print(f"❌ 命令同步失败: {e}")
    
    # 设置状态
    await bot.change_presence(activity=discord.Game(name="Catiecli | /register"))


@bot.tree.command(name="register", description="📝 注册 Catiecli 账号")
async def register_command(interaction: discord.Interaction):
    """注册命令"""
    # 检查是否已注册
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_BASE_URL}/api/auth/check-discord/{interaction.user.id}"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("exists"):
                        embed = discord.Embed(
                            title="ℹ️ 您已注册",
                            description=f"您的账号: **{data.get('username')}**\n使用 `/key` 获取 API Key",
                            color=discord.Color.blue()
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return
    except:
        pass
    
    await interaction.response.send_modal(RegisterModal())


@bot.tree.command(name="key", description="🔑 获取您的 API Key")
async def get_key_command(interaction: discord.Interaction):
    """获取 API Key"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_BASE_URL}/api/auth/discord-key/{interaction.user.id}"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    embed = discord.Embed(
                        title="🔑 您的 API Key",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="用户名", value=data.get("username"), inline=True)
                    embed.add_field(name="今日用量", value=f"{data.get('today_usage', 0)}/{data.get('daily_quota', 100)}", inline=True)
                    embed.add_field(name="API Key", value=f"```{data.get('api_key')}```", inline=False)
                    embed.add_field(
                        name="API 地址",
                        value=f"```{API_PUBLIC_URL}```\n💡 直接填域名即可，无需添加 /v1",
                        inline=False
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message("❌ 您还没有注册，请使用 `/register` 注册", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 获取失败: {str(e)}", ephemeral=True)


@bot.tree.command(name="resetkey", description="🔄 重新生成 API Key")
async def resetkey_command(interaction: discord.Interaction):
    """重新生成 API Key"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE_URL}/api/auth/discord-key/{interaction.user.id}/regenerate"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    embed = discord.Embed(
                        title="🔄 API Key 已重新生成",
                        description="⚠️ 旧密钥已失效，请使用新密钥！",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="用户名", value=data.get("username"), inline=True)
                    embed.add_field(name="新 API Key", value=f"```{data.get('api_key')}```", inline=False)
                    embed.add_field(
                        name="API 地址",
                        value=f"```{API_PUBLIC_URL}```",
                        inline=False
                    )
                    embed.set_footer(text="请妥善保管您的新 API Key")
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message("❌ 您还没有注册，请使用 `/register` 注册", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 重新生成失败: {str(e)}", ephemeral=True)


@bot.tree.command(name="stats", description="📊 查看使用统计")
async def stats_command(interaction: discord.Interaction):
    """查看统计"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_BASE_URL}/api/auth/discord-stats/{interaction.user.id}"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    embed = discord.Embed(
                        title="📊 使用统计",
                        color=discord.Color.purple()
                    )
                    embed.add_field(name="用户名", value=data.get("username"), inline=True)
                    embed.add_field(name="今日用量", value=f"{data.get('today_usage', 0)}/{data.get('daily_quota', 100)}", inline=True)
                    embed.add_field(name="总请求数", value=data.get("total_requests", 0), inline=True)
                    embed.add_field(name="贡献凭证", value=data.get("credentials_count", 0), inline=True)
                    embed.add_field(name="账号状态", value="✅ 正常" if data.get("is_active") else "❌ 禁用", inline=True)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message("❌ 您还没有注册", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 获取失败: {str(e)}", ephemeral=True)


@bot.tree.command(name="setup", description="🛠️ 发送注册面板")
async def setup_command(interaction: discord.Interaction):
    """设置注册面板"""
    embed = discord.Embed(
        title="🐱 欢迎使用 Catiecli",
        description="Catiecli 是一个 Gemini API 代理服务，让您轻松使用 AI 能力。\n\n"
                    "**功能特点:**\n"
                    "• 🚀 OpenAI 兼容 API\n"
                    "• 🎁 贡献凭证获得更多额度\n"
                    "• 📊 实时使用统计\n\n"
                    "点击下方按钮开始注册！",
        color=discord.Color.purple()
    )
    embed.set_footer(text="一个 Discord 账号只能注册一个 Catiecli 账号")
    
    await interaction.channel.send(embed=embed, view=RegisterButton())
    await interaction.response.send_message("✅ 注册面板已发送！", ephemeral=True)


@bot.tree.command(name="donate", description="🎁 贡献凭证获取 OAuth 链接")
async def donate_command(interaction: discord.Interaction):
    """获取 OAuth 链接贡献凭证"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_BASE_URL}/api/oauth/auth-url-public?get_all_projects=false"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    embed = discord.Embed(
                        title="🎁 贡献凭证",
                        description="通过 Google OAuth 授权贡献您的凭证，获得额度奖励！",
                        color=discord.Color.gold()
                    )
                    embed.add_field(
                        name="第1步：授权",
                        value=f"[👉 点击这里授权]({data.get('auth_url')})",
                        inline=False
                    )
                    embed.add_field(
                        name="第2步：复制回调 URL",
                        value="授权后会跳转到一个打不开的页面，复制浏览器地址栏的完整 URL",
                        inline=False
                    )
                    embed.add_field(
                        name="第3步：提交",
                        value="使用 `/callback` 命令粘贴回调 URL 完成绑定",
                        inline=False
                    )
                    embed.set_footer(text="贡献凭证后可使用公共凭证池，并获得更高的速率限制")
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message("❌ 获取授权链接失败", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 获取失败: {str(e)}", ephemeral=True)


class CallbackModal(discord.ui.Modal, title="🔗 粘贴回调 URL"):
    """回调 URL 输入表单"""
    callback_url = discord.ui.TextInput(
        label="回调 URL (以 http://localhost:8080 开头)",
        placeholder="http://localhost:8080/?code=...",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
                async with session.post(
                    f"{API_BASE_URL}/api/oauth/from-callback-url-discord",
                    json={
                        "callback_url": str(self.callback_url),
                        "discord_id": str(interaction.user.id),
                        "is_public": True
                    }
                ) as resp:
                    data = await resp.json()
                    
                    if resp.status == 200:
                        embed = discord.Embed(
                            title="🎉 凭证贡献成功！",
                            color=discord.Color.green()
                        )
                        embed.add_field(name="邮箱", value=data.get("email", "未知"), inline=True)
                        embed.add_field(name="等级", value=f"{'⭐ 3.0' if data.get('model_tier') == '3' else '2.5'}", inline=True)
                        if data.get("reward_quota"):
                            embed.add_field(name="奖励额度", value=f"+{data.get('reward_quota')}", inline=True)
                        embed.set_footer(text="感谢您的贡献！现在可以使用公共凭证池了")
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        error_msg = data.get("detail", "提交失败")
                        await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 请求失败: {str(e)}", ephemeral=True)


@bot.tree.command(name="callback", description="🔗 粘贴 OAuth 回调 URL 完成凭证贡献")
async def callback_command(interaction: discord.Interaction):
    """提交 OAuth 回调 URL"""
    await interaction.response.send_modal(CallbackModal())


# 持久化按钮
@bot.event
async def setup_hook():
    bot.add_view(RegisterButton())


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ 请设置 DISCORD_TOKEN 环境变量")
        exit(1)
    bot.run(DISCORD_TOKEN)
