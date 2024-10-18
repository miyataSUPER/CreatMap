import streamlit as st
import googlemaps
import folium
from streamlit_folium import folium_static
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
import pandas as pd

def get_api_key():
    """Google Maps APIキーを取得する"""
    return st.text_input('Google Maps APIキーを入力してください', type='password')

def get_address():
    """企業の住所を取得する"""
    return st.text_input('企業の住所を入力してください')

def get_genres():
    """検索する場所のジャンルを日本語で複数選択"""
    genre_dict = {
        '飲食店': 'restaurant',
        'カフェ': 'cafe',
        'バー': 'bar',
        'コンビニ': 'convenience_store',
        'ガソリンスタンド': 'gas_station',
        'ホテル': 'lodging',
        '銀行': 'bank',
        '病院': 'hospital',
        '薬局': 'pharmacy',
        '映画館': 'movie_theater',
        '公園': 'park',
        '図書館': 'library',
        'ショッピングモール': 'shopping_mall',
        '美術館': 'museum',
        '駅': 'train_station',
        'バス停': 'bus_station'
    }
    genres_jp = st.multiselect('検索するジャンルを選択してください（複数選択可）', list(genre_dict.keys()), default=['飲食店'])
    genres = [genre_dict[genre] for genre in genres_jp]
    return genres, genres_jp

def get_location(gmaps, address):
    """
    住所から緯度経度を取得する
    """
    geocode_result = gmaps.geocode(address)
    if geocode_result:
        location = geocode_result[0]['geometry']['location']
        return location['lat'], location['lng']
    return None

def get_nearby_places(gmaps, location, place_types, radius=500):
    """
    指定された位置の周辺にある場所を取得する
    """
    places_result = []
    seen_place_ids = set()  # 重複を避けるためにPlace IDを記録

    for place_type in place_types:
        next_page_token = None

        while True:
            if next_page_token:
                response = gmaps.places_nearby(
                    location=location,
                    radius=radius,
                    type=place_type,
                    page_token=next_page_token,
                    language='ja'  # 結果を日本語で取得
                )
            else:
                response = gmaps.places_nearby(
                    location=location,
                    radius=radius,
                    type=place_type,
                    language='ja'  # 結果を日本語で取得
                )
            for place in response['results']:
                place_id = place['place_id']
                if place_id not in seen_place_ids:
                    places_result.append(place)
                    seen_place_ids.add(place_id)
            next_page_token = response.get('next_page_token')

            if not next_page_token:
                break
            time.sleep(2)  # APIの制限を考慮して待機

    return places_result

def get_place_details(gmaps, place_id):
    """
    Place Details APIを使用して店舗の詳細情報を取得する
    """
    details = gmaps.place(
        place_id=place_id,
        language='ja',
        fields=['opening_hours']
    )
    return details.get('result', {}).get('opening_hours', {})

def create_place_list(gmaps, places):
    """
    場所のリストを作成する
    """
    place_list = []
    for idx, place in enumerate(places):
        # 各店舗の詳細情報を取得
        opening_hours = get_place_details(gmaps, place['place_id'])
        time.sleep(0.1)  # API利用制限を考慮して遅延を追加

        weekday_text = opening_hours.get('weekday_text', [])

        # 初期化
        business_hours_weekdays = set()
        business_hours_weekends = set()
        closed_days = []

        # 曜日のマッピング
        day_to_index = {
            '月曜日': 0,
            '火曜日': 1,
            '水曜日': 2,
            '木曜日': 3,
            '金曜日': 4,
            '土曜日': 5,
            '日曜日': 6
        }

        for day_info in weekday_text:
            # "月曜日: 9時00分～17時00分" の形式を分割
            if ': ' in day_info:
                day, hours = day_info.split(': ', 1)
                if hours == '定休日':
                    closed_days.append(day)
                else:
                    if day in ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日']:
                        business_hours_weekdays.add(hours)
                    elif day in ['土曜日', '日曜日']:
                        business_hours_weekends.add(hours)

        # 平日営業時間の設定
        if business_hours_weekdays:
            if len(business_hours_weekdays) == 1:
                hours_weekdays = business_hours_weekdays.pop()
            else:
                hours_weekdays = '曜日によって異なります'
        else:
            hours_weekdays = '情報なし'

        # 休日営業時間の設定
        if business_hours_weekends:
            if len(business_hours_weekends) == 1:
                hours_weekends = business_hours_weekends.pop()
            else:
                hours_weekends = '曜日によって異なります'
        else:
            hours_weekends = '情報なし'

        # 定休日の設定
        closed_days_str = ', '.join(closed_days) if closed_days else 'なし'

        place_info = {
            '番号': idx + 1,
            '名称': place['name'],
            '住所': place.get('vicinity', ''),
            '平日営業時間': hours_weekdays,
            '休日営業時間': hours_weekends,
            '定休日': closed_days_str
        }
        # 緯度と経度は地図表示のために保持
        place_info['緯度'] = place['geometry']['location']['lat']
        place_info['経度'] = place['geometry']['location']['lng']
        place_list.append(place_info)
    return place_list

def create_map(lat, lng, place_list):
    """
    Foliumを使用して地図を作成する
    """
    m = folium.Map(location=[lat, lng], zoom_start=16, control_scale=True)

    # 企業の位置にマーカーを追加
    folium.Marker(
        [lat, lng],
        popup='企業の位置',
        icon=folium.Icon(color='black', icon='building', prefix='fa')
    ).add_to(m)

    # 場所に番号付きのマーカーを追加
    for place in place_list:
        folium.Marker(
            [place['緯度'], place['経度']],
            icon=folium.DivIcon(html=f"""
                <div style="
                    font-size: 10pt;
                    color: black;
                    text-align: center;
                    line-height: 15px;
                    background-color: white;
                    border: 2px solid black;
                    border-radius: 50%;
                    width: 30px;
                    height: 30px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                ">
                    {place['番号']}
                </div>
            """),
            popup=f"{place['名称']}\n{place['住所']}",
            tooltip=str(place['番号'])
        ).add_to(m)

    return m

def save_map_as_image(m):
    """
    地図を画像として保存する
    """
    m.save('map.html')

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=800,600')

    driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
    driver.get('file://' + os.path.abspath('map.html'))

    time.sleep(5)  # 地図の読み込みを待機

    driver.save_screenshot('map.png')
    driver.quit()

    st.image('map.png', caption='地図の画像', use_column_width=True)
    st.success('地図を画像として保存しました。')

def main():
    st.title('企業周辺の場所リストと地図表示アプリ')

    api_key = get_api_key()
    if not api_key:
        return

    gmaps = googlemaps.Client(key=api_key)

    address = get_address()
    if not address:
        return

    place_types, place_types_jp = get_genres()

    try:
        location = get_location(gmaps, address)
        if not location:
            st.error('住所から位置情報を取得できませんでした。')
            return

        lat, lng = location
        st.success(f'企業の位置を取得しました。緯度: {lat}, 経度: {lng}')

        places = get_nearby_places(gmaps, location, place_types)
        if not places:
            st.warning(f'半径500m以内に選択されたジャンルの場所が見つかりませんでした。')
            return

        # 進捗状況を表示するプログレスバーを追加
        progress_bar = st.progress(0)
        total_places = len(places)
        place_list = create_place_list(gmaps, places)
        progress_bar.progress(1.0)

        st.subheader('場所リスト')

        # 表示用のデータフレームを作成（緯度・経度を除外）
        df = pd.DataFrame(place_list)
        df_display = df.drop(columns=['緯度', '経度'])
        st.table(df_display)

        # CSVダウンロードボタン
        csv = df_display.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label='リストをCSVとしてダウンロード',
            data=csv,
            file_name='場所リスト.csv',
            mime='text/csv'
        )

        m = create_map(lat, lng, place_list)

        st.subheader('場所マップ')
        folium_static(m)

        if st.button('地図を画像として保存'):
            save_map_as_image(m)

    except Exception as e:
        st.error(f'エラーが発生しました: {e}')

if __name__ == '__main__':
    main()
