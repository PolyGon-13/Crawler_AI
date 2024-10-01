import urllib.request
import datetime
import time
import json
import aiohttp
import asyncio
import nest_asyncio # 구글 코랩 환경인 경우 추가
import gradio as gr
from openai import OpenAI
from newspaper import Article,Config

nest_asyncio.apply() # 구글 코랩 환경인 경우 추가

client_id="key1" # naver client_id api
client_secret="key2" # naver client_secret api 
api_key="key3" # gpt api

client=OpenAI(api_key=api_key)

# API 요청 URL 생성 및 요청 함수
def get_RequestURL(url):
    req=urllib.request.Request(url) # urllib.request 함수를 통해 url을 받음
    req.add_header("X-Naver-Client-Id",client_id) # 클라이언트 아이디를 입력받음
    req.add_header("X-Naver-Client-Secret",client_secret) # 클라이언트 시크릿을 입력받음

    try:
        response = urllib.request.urlopen(req)
        if response.getcode()==200: # 요청 성공
            # print("[%s] Url Request Success" % datetime.datetime.now()) # 보낸 시간 출력
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        if e.code==429: # API 요청 한도 초과
            # print("Request limit reached. Waiting for retry...")
            time.sleep(60) # 60초 대기
            return get_RequestURL(url) # 재시도
    except Exception as e:
        # print(e)
        # print("[%s] Error for URL: %s"%(datetime.datetime.now(),url))
        return None

# 네이버 검색 API 호출 함수
def getNaverSearch(node,search,start,display):
    base="https://openapi.naver.com/v1/search"
    node="/%s.json"%node
    parameters="?query=%s&start=%s&display=%s"%(urllib.parse.quote(search),start,display)
    url=base+node+parameters

    responseDecode=get_RequestURL(url)
    if (responseDecode==None):
        return None
    else:
        return json.loads(responseDecode)

# 기사 정보 추출 함수
def getPostData(post,jsonResult,cnt,news_arr):
    title=post['title']
    link=post['link']
    pDate=datetime.datetime.strptime(post['pubDate'],'%a, %d %b %Y %H:%M:%S +0900')
    pDate=pDate.strftime('%Y-%m-%d %H:%M:%S')
    # org_link=post['originallink']
    # description=post['description']

    jsonResult.append({'cnt':cnt,'title':title,'link':link,'pDate':pDate}) # 번호, 제목, 링크, 날짜 저장
    news_arr.append(link) # 링크 저장

    return

async def fetch_article(url,session,summarize):
    config=Config()
    config.browser_user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.121 Safari/537.36'
    config.request_timeout=15

    try:
        async with session.get(url,ssl=False) as response:
            article=Article(url,config=config)
            article.set_html(await response.text())
            article.parse()
            summarize.append(article.text)
    except Exception as e:
        print(f"Failed to download article at {url}. Error: {e}")

async def extract_text_from_url_async(news_arr,summarize):
    async with aiohttp.ClientSession() as session:
        tasks=[fetch_article(url,session,summarize) for url in news_arr]
        await asyncio.gather(*tasks)

'''
def extract_text_from_url(news_arr,summarize):
    config=Config()
    config.browser_user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.121 Safari/537.36'
    config.request_timeout=15

    with open('news_text.txt','w',encoding='utf-8') as file:
        for url in news_arr:
            article=Article(url,config=config)
            try:
                article.download()
                article.parse()
                summarize.append(article.text) # 기사 본문을 summarize 리스트에 저장
                #file.write(article.text+'\n\n')
                #print(article.text)
            except Exception as e:
                print(f"Failed to download article at {url}. Error: {e}")

    print("Summarize Success")
'''

def news_summarize(prompt,model="gpt-4o-mini",max_tokens=1000,temperature=0.7,top_p=1.0,frequency_penalty=0.0,presence_penalty=0.0):
    response=client.chat.completions.create(
        messages=[
            {"role":"system","content":"You are a newspaper summarizer."},
            {"role":"user","content":prompt}
        ],
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
    )
    return response

def request_gpt(summarize,search):
    for text in summarize:
        prompt=f"{text}. 당신은 위의 {search}와 관련된 기사들만을 찾아내어 요약해야 합니다. 관련 없는 내용은 배제하고 관련 있는 내용들을 모두 함축하고 최근의 동향을 빠르게 파악할 수 있도록 내용보다는 사건 위주의 리스트 형식으로 요약해주세요."
        dialogue=news_summarize(prompt)

    output=""
    with open('news_summary.txt','a',encoding='utf-8') as file:
        for choice in dialogue.choices:
            message_content=choice.message.content.strip()
            file.write(message_content+'\n\n')
            output+=message_content
            # print(message_content)

    total_tokens=dialogue.usage.total_tokens
    # print(f"Total tokens used: {total_tokens}")

    return output

def search_and_summarize(search):
    node='news'
    # search= input('검색어를 입력하세요: ')
    cnt=0
    data_limit=100 # 수집할 데이터 개수
    jsonResult=[]
    news_arr=[]
    summarize=[]

    jsonResponse=getNaverSearch(node,search,1,100) # 한 번에 수집할 데이터 개수 (1번에 10개씩 수집)
    if jsonResponse is None:
        # print("Failed to get response from Naver API")
        return

    total=jsonResponse['total']
    total_pages=min(data_limit//100,total//100)

    while ((jsonResponse is not None) and (jsonResponse['display']!=0) and cnt<data_limit): # API 요청이 실패하거나 데이터가 없는 경우에 break
        for post in jsonResponse['items']:
            cnt+=1
            getPostData(post,jsonResult,cnt,news_arr)

        if cnt>=data_limit:
            break

        start=jsonResponse['start']+jsonResponse['display']
        jsonResponse=getNaverSearch(node,search,start,100)

    # print('Search %d Data'%total)

    with open('%s_%s.json'%(search,node),'w',encoding='utf8') as outfile:
        jsonFile = json.dumps(jsonResult,indent=4,sort_keys=True,ensure_ascii=False)
        outfile.write(jsonFile)

    # print("Collect %d Data"%cnt)
    # print('%s_%s.json SAVED'%(search,node))

    # print('Summarize Data...')
    asyncio.run(extract_text_from_url_async(news_arr,summarize))
    summary_result=request_gpt(summarize,search)

    # 수집한 URL 전부 출력
    # for i in news_arr:
        # print(i)
    
    return summary_result

iface = gr.Interface(fn=search_and_summarize,
                inputs=gr.Textbox(label="키워드를 입력하세요."),
                outputs=gr.Textbox(label="요약 결과"),
                title="밀리서치",
                description="키워드를 입력하면 관련 뉴스 기사를 요약합니다.",
                allow_flagging=False)

if __name__ == '__main__':
    iface.launch()
