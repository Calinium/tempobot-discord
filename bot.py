from os import environ
import dotenv
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from googleapiclient.discovery import build
from youtube_dl import YoutubeDL #version 2021.12.17

bot = commands.Bot(command_prefix='$', intents=discord.Intents.all())

dotenv_file = dotenv.find_dotenv()
dotenv.load_dotenv(dotenv_file)

DISCORD_TOKEN = environ["TOKEN"]
youtube_api_key = environ["YOUTUBE_API_KEY"]

youtube = build('youtube','v3', developerKey=youtube_api_key)

YDL_OPTIONS = {'format': 'bestaudio', 'noplaylist':'True'}

FFMPEG_OPTIONS = {
    'options': '-vn',
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
}

songQueue: dict[int, list:str] = {} #서버별 큐를 따로 관리, 각 서버에서 사용되는 큐는 리스트로 관리
loop: dict[int, int] = {} #0: 없음 | 1:한곡 루프 | 2:큐 루프 ##서버별 루프 따로 관리

def getURL(urlANDtitle: str):
        url = urlANDtitle.split("#SpAcEoFuRlAnDtItLe#")[0]
        return url

def getTITLE(urlANDtitle: str):
        title = urlANDtitle.split("#SpAcEoFuRlAnDtItLe#")[1]
        return title

def resetQueue(guildID: int):
    songQueue[guildID] = []
    loop[guildID] = 0

@bot.event
async def on_ready():
    print("Connecting to TempoBot")
    try:
        synced = await bot.tree.sync()
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.listening, name="/help")
            )
        print(f"Synced {len(synced)} command(s)")
        print("==============================")
    except Exception as e:
        print(e)

@bot.event
async def on_voice_state_update(member, before, after):
    bot_connection = member.guild.voice_client
    if (before.channel != None ) and (bot_connection!=None):
        #봇과 사람값이 존재할 때:
        if bot_connection.channel == before.channel:
            #봇이 참여중이고 봇의 채널과 사람이 나간 채널이 일치하면:
            for mem in before.channel.members:
                if (mem.bot==False): #한명이라도 사람이라면
                    return
            #for문 끝날때까지 사람 검색을 못하면
            print(f"{bot_connection.channel}에서 연결 종료함.")
            await bot_connection.disconnect()
            resetQueue(member.guild.id)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(embed = discord.Embed(description = f'*{ctx.message.content}* 은(는) 존재하지 않는 명령어입니다.', color = discord.Color.red()))
    else:
        print(error)

@bot.tree.command(name="ping", description='현재 핑을 보여줍니다')
async def ping(i: discord.Interaction):
    await i.response.send_message(f"퐁! `{round(bot.latency * 1000)}ms`")

@bot.tree.command(name='help', description='템포봇의 명령어를 보여줍니다') 
async def help(i:discord.Interaction):
    embed=discord.Embed(title="Tempo", color=0xf3bb76)
    embed.set_thumbnail(url=bot.user.avatar)
    embed.add_field(name='help', value= 'Tempo 사용법 안내 (**[]**안에 들어있는 명령어로도 사용이 가능합니다)', inline = False)
    embed.add_field(name='참여', value='음성 채널에 들어갑니다', inline = False)
    embed.add_field(name='나가', value='현재 속해있는 음성 채널에서 나갑니다', inline = False)
    embed.add_field(name='p', value='Youtube에서 음악을 검색하여 재생합니다', inline = False)
    embed.add_field(name='s', value='재생중인 음악을 스킵합니다', inline = False)
    embed.add_field(name='정지', value='재생중인 음악을 정지합니다', inline = False)
    embed.add_field(name='재개', value='정지된 음악을 재생합니다', inline = False)
    embed.add_field(name='l', value='하나의 음악을 반복재생합니다', inline = False)
    embed.add_field(name='lq', value='플레이리스트를 반복재생합니다', inline = False)
    embed.add_field(name='q', value='현재 재생목록을 확인합니다', inline = False)
    embed.add_field(name='reset', value='봇이 고장났을 때 초기화시킵니다', inline = False)
    await i.response.send_message("**DM을 확인해주세요 😄", ephemeral=False)
    dm_channel = await i.user.create_dm()
    await dm_channel.send(embed=embed)

@bot.tree.command(name='참여', description='음성 채널에 들어갑니다')
async def join(i: discord.Interaction): 
    vc = i.guild.voice_client
    voice = i.user.voice
    if voice == None:
        await i.response.send_message('❌ 먼저 음성 채널에 접속해 주세요')
        return
    channel = voice.channel
    if vc and vc.is_connected():
        await i.response.send_message(f'**이미 연결되어 있음')
    elif vc == None:
        await channel.connect()
        resetQueue(i.guild_id)
        await i.response.send_message(f'✅**{channel}** 연결됨')
    else:
        await vc.move_to(channel)
        resetQueue(i.guild_id)
        await i.response.send_message(f'✅**{channel}** 연결됨')

@bot.tree.command(name='나가', description='현재 속해있는 음성 채널에서 나갑니다')
async def leave(i: discord.Interaction):
    vc = i.guild.voice_client
    if vc == None:
        await i.response.send_message('❌ 연결되어있는 채널이 없습니다')
    else:
        await vc.disconnect()
        await i.response.send_message('✅ 연결 종료됨')
        resetQueue(i.guild_id)
        
@bot.tree.command(name='재개',description='정지된 음악을 재생시킵니다')
async def resume(i: discord.Interaction):
    global songQueue
    vc = i.guild.voice_client
    if vc == None:
        await i.response.send_message('❌ 연결되어있는 채널이 없습니다')
        return

    if not vc.is_playing() and songQueue[i.guild_id] != [] : #큐에 음악이 있지만 음악 재생중이 아님
        vc.resume()
        await i.response.send_message('✅ 음악 재생')
    elif songQueue[i.guild_id] == []: #큐에 음악이 없음
        await i.response.send_message('❌ 중단된 음악이 없습니다')
    else: #음악이 재생중임
        await i.response.send_message('❌ 음악이 이미 재생중입니다')

@bot.tree.command(name='정지', description='재생중인 음악을 일시정지합니다')
async def pause(i: discord.Interaction):
    global songQueue
    vc = i.guild.voice_client
    if vc == None:
        await i.response.send_message('❌ 연결되어있는 채널이 없습니다')
        return

    if vc.is_playing() and songQueue[i.guild_id] != []: #음악이 재생중이고 큐에 음악이 있음
        vc.pause()
        await i.response.send_message('✅ 음악 일시정지됨')
    elif songQueue[i.guild_id] == []: #큐에 음악이 없음
        await i.response.send_message('❌ 재생 중인 음악이 없습니다')
    else: #음악이 재생중임
        await i.response.send_message('❌ 음악이 이미 재생중입니다')

@bot.tree.command(name='p',description='Youtube에서 음악을 검색하여 재생합니다')
@app_commands.describe(search="검색할 음악을 입력하세요")
async def play(i: discord.Interaction, search: str):
    global songQueue

    vc = i.guild.voice_client
    voice = i.user.voice
    if voice == None:
        await i.response.send_message('❌ 먼저 음성 채널에 접속해 주세요')
        return
    channel = voice.channel
    if vc == None:
        await channel.connect()
    else:
        await vc.move_to(channel)

    vc = i.guild.voice_client #vc 업데이트

    await i.response.defer() # 생각 시작

    search_response = youtube.search().list( #음악 검색
        q = search,
        order = "relevance",
        part = "snippet",
        maxResults = 3
    ).execute()
    for result in search_response['items']: #나온 결과들을 하나하나 분석함
        try: #비디오 링크 제작 시도
            videolink = ('https://www.youtube.com/watch?v=' + result['id']['videoId'])
            title: str = result['snippet']['title']
            title.replace("&#39;", "'")
            break
        except: 
            pass
    if videolink == '':
        await i.followup.send('❌ 죄송합니다. 음악을 찾지 못했습니다')
        return

    with YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(videolink, download=False) #만들어진 비디오링크로 음악 정보를 추출함
        except commands.CommandInvokeError:
            await i.followup.send('❌ 죄송합니다. 음악을 찾지 못했습니다')
            return

    url = info['formats'][0]['url']

    try:
        loop[i.guild_id]
    except KeyError:
        loop[i.guild_id] = 0

    try:
        songQueue[i.guild_id].append(url+"#SpAcEoFuRlAnDtItLe#"+title)
    except KeyError:
        songQueue[i.guild_id] = [url+"#SpAcEoFuRlAnDtItLe#"+title]        

    print(songQueue)

    if vc.is_playing() or len(songQueue[i.guild_id]) >= 2:
        await i.followup.send(content= f'✅ 재생목록에 추가됨 : **{title}**')
    else:
        await i.followup.send(content= f'✅ 재생 중 : **{title}**')
        vc.play(discord.FFmpegPCMAudio(source=getURL(songQueue[i.guild_id][0]), **FFMPEG_OPTIONS), after = lambda e: check_q())

    def check_q():
        global songQueue
        global loop
        try:
            if loop[i.guild_id] == 1: #한곡 루프일때
                vc.play(discord.FFmpegPCMAudio(source=getURL(songQueue[i.guild_id][0]), **FFMPEG_OPTIONS), after = lambda e: check_q()) #큐의 맨 앞 곡 재생
            elif loop[i.guild_id] == 2: #큐 루프일때
                tempSong = songQueue[i.guild_id][0] #맨 앞 곡 임시저장
                del songQueue[i.guild_id][0] #큐의 첫번째 곡 제거
                songQueue[i.guild_id].append(tempSong) #큐의 맨 뒤에 임시 곡 추가
                vc.play(discord.FFmpegPCMAudio(source=getURL(songQueue[i.guild_id][0]), **FFMPEG_OPTIONS), after = lambda e: check_q()) #큐의 맨 앞 곡 재생
            else: #루프가 없을 때
                del songQueue[i.guild_id][0]
                vc.play(discord.FFmpegPCMAudio(source=getURL(songQueue[i.guild_id][0]), **FFMPEG_OPTIONS), after = lambda e: check_q())
        except IndexError:
            pass

@bot.tree.command(name='s', description='재생중인 음악을 스킵합니다')
async def skip(i: discord.Interaction):
    global songQueue
    global loop
    vc = i.guild.voice_client
    if vc == None:
        await i.response.send_message('❌ 연결되어있는 채널이 없습니다')
        return

    if vc.is_playing():
        if loop[i.guild_id] == 1:
            loop[i.guild_id] = 0
            vc.stop()
            await asyncio.sleep(1)
            loop[i.guild_id] = 1
        else:
            vc.stop()
        await i.response.send_message('✅ 스킵됨')
    else:
        await i.response.send_message('❌ 재생 중인 음악이 없습니다')

@bot.tree.command(name='l',description='하나의 음악을 반복재생합니다')
async def loop_(i: discord.Interaction):
    global loop
    if loop[i.guild_id] == 0 or loop[i.guild_id] == 2:
        loop[i.guild_id] = 1
        await i.response.send_message('🔂 루프 켜짐')
    else:
        loop[i.guild_id] = 0
        await i.response.send_message('🔂 루프 꺼짐')

@bot.tree.command(name='lq',description='현재 저장된 트랙을 반복재생합니다')
async def loop_queue(i: discord.Interaction):
    global loop
    if loop[i.guild_id] == 0 or loop[i.guild_id] == 1:
        loop[i.guild_id] = 2
        await i.response.send_message('🔁 루프 큐 켜짐')
    else:
        loop[i.guild_id] = 0
        await i.response.send_message('🔁 루프 큐 꺼짐')

@bot.tree.command(name='q', description='재생목록을 확인합니다')
async def queue(i: discord.Interaction):
    global songQueue
    global loop
    if songQueue[i.guild_id] == []: #큐에 음악이 없을 때
        await i.response.send_message('❌ 재생 중인 음악이 없습니다')
    else:
        if loop[i.guild_id] == 1:
            embed = discord.Embed(title='', description=f'**{getTITLE(songQueue[i.guild_id][0])}** 🔂', color = 0xffffff)
        elif loop[i.guild_id] == 2:
            embed = discord.Embed(title='', description=f'**{getTITLE(songQueue[i.guild_id][0])}** 🔁', color = 0xffffff)
        else:
            embed = discord.Embed(title='', description=f'**{getTITLE(songQueue[i.guild_id][0])}**', color = 0xffffff)

        embed.set_author(name='지금 재생 중', icon_url=bot.user.avatar)
        embed.set_footer(text=i.user, icon_url=i.user.avatar)
        count: int = 0
        for song in songQueue[i.guild_id]:
            count+=1
            if count != 1:
                embed.add_field(name=f'Track {count}', value=f'{getTITLE(song)}', inline=False)
        await i.response.send_message(embed=embed)

@bot.tree.command(name='reset', description='봇이 고장났을 때, 초기화시킵니다')
async def reset(i: discord.Interaction):
    global songQueue
    global loop
    vc = i.guild.voice_client
    if vc.is_connected():
        if vc.is_playing():
            vc.stop()
        await vc.disconnect()
    resetQueue(i.guild_id)
    await i.response.send_message('✅ 초기화 완료')

bot.run(DISCORD_TOKEN)