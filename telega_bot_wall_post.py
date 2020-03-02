#!/usr/bin/python
# -*- coding: UTF-8 -*-
from datetime import datetime, timedelta

import random

import time

import requests
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import w_watermark, b_watermark, akk_for_comment, list_groups, \
    SQLALCHEMY_DATABASE_URI, max_count_post, hash_list, id_owner_group, id_user_debug, telegram_token_news_bayanist_bot, \
    REQUEST_KWARGS

import vk as vk

from app.models import Hash, Post, Groups

from py_telegram_bot.bot import Bot

engine = create_engine(SQLALCHEMY_DATABASE_URI, echo=True)
Session = sessionmaker(bind=engine)

session_vk = vk.SessionVk()
vk_api = vk.VkApi(session_vk)


def add_watermark(image, path):
    count_dark = 0

    for y in range(27):
        for x in range(92):
            rgb = image.getpixel((x, y))
            if rgb[0] < 127 or rgb[1] < 127 or rgb[2] < 127:
                count_dark += 1

    if count_dark < 900:
        watermark = b_watermark
    else:
        watermark = w_watermark

    layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
    layer.paste(watermark, (2, 2))

    Image.composite(layer, image, layer).save(path)


def get_most_like_post(wall_records, group_name):
    # noinspection PyGlobalUndefined
    global now_img_hash, now_post_id

    index_record = []
    for record in wall_records['items'][1:]:
        not_only_photo = False
        if 'copy_owner_id' in record:
            continue
        if 'attachments' in record and '/' not in record['text'] and record['marked_as_ads'] == 0:
            if record['likes']['count'] >= 100:
                if record['attachments'].__len__() <= 10:
                    for attach in record['attachments']:
                        if attach['type'] != 'photo':
                            not_only_photo = True
                            break
                    if not_only_photo:
                        print('в этом посте не только фотки')
                        continue
                    else:
                        match = None

                        for attach in record['attachments']:
                            try:
                                img_content = requests.get(attach['photo']['sizes'][-1:][0]['url'])
                                match = find_match(img_content.content, record)
                                if match is not None:
                                    break
                            except Exception as e:
                                print('по каким то не понятным причинам не удалось скачать картинку для проверки')
                                match = None
                        if match is None:
                            index_record.append([record['likes']['count'], record])
                else:
                    if record['attachments'][0]['type'] == 'photo':

                        try:
                            img_content = requests.get(record['attachments'][0]['photo']['src_big'])
                            match = find_match(img_content.content, record)
                        except Exception as e:
                            print('по каким то не понятным причинам не удалось скачать картинку для проверки')

                            match = None
                        if match is None:
                            index_record.append([record['likes']['count'], record])
                    else:
                        print('в этом посте не только фотки')
            else:
                print('у этого посте всего (' + str(record['likes']['count']) + ') лайков')

    index_record.sort(key=lambda x: x[0])

    if index_record.__len__() == 0:
        print('в группе (' + group_name + ') ни чего интересного')
        _rec = None
    else:
        _rec = index_record[index_record.__len__() - 1]
        _rec[1]['text'] = _rec[1]['text'].replace('<br>', ' ')
        now_img_hash, now_post_id = _rec[1]['img_hash'], _rec[1]['post_id']

    return _rec


def save_photo_for_post(post):
    photos = ''

    for count, attach in enumerate(post[1]['attachments']):
        try:
            path = 'photo_for_post/photo' + str(count) + '.jpeg'
            img_content = requests.get(attach['photo']['sizes'][-1:][0]['url'])

            img_file = open(path, 'wb')
            img_file.write(img_content.content)
            img_file.close()

            add_watermark(Image.open(path), path)

            photos += path
            if count < post[1]['attachments'].__len__() - 1:
                photos += ','
        except Exception as e:
            print('не смогли сохранить пикчу для поста')

    return photos


def distance(a, b):
    """вычисление расстояния Левенштейна между a и b"""
    n, m = len(a), len(b)
    if n > m:
        # Make sure n <= m, to use O(min(n,m)) space
        a, b = b, a
        n, m = m, n

    current_row = range(n + 1)  # Keep current and previous row, not entire matrix
    for i in range(1, m + 1):
        previous_row, current_row = current_row, [i] + [0] * n
        for j in range(1, n + 1):
            add, delete, change = previous_row[j] + 1, current_row[j - 1] + 1, previous_row[j - 1]
            # noinspection PyUnresolvedReferences
            if a[j - 1] != b[i - 1]:
                change += 1
            current_row[j] = min(add, delete, change)

    return current_row[n]


def find_match(img_content, post):
    # noinspection PyGlobalUndefined
    global hash_list
    size = 8, 8
    _hash = ''
    content = img_content

    match = None
    session = Session()
    for id_post, in session.query(Post.id_post).filter(Post.id_post == str(post['id']) + str(post['from_id'])):
        match = id_post

    if match is None:
        with open('test.jpeg', 'wb') as out_file:
            out_file.write(content)

        image = Image.open("test.jpeg")  # Открываем изображение.
        image = image.resize(size, Image.BILINEAR)

        _hash = get_hash(image)

        del image

        if _hash is None:
            return 1

        for h in hash_list:
            if isinstance(h.hash, str):
                current_row = distance(h.hash, _hash)
                if current_row <= 1:
                    match = 1
                    print(h.hash + ' - ' + _hash + ' ' + str(current_row))
                    break

    post['post_id'] = str(post['id']) + str(post['from_id'])
    post['img_hash'] = _hash

    return match


def base_convert(number, from_base, to_base):  # процедура для конвертации в шеснадцетиричную систему
    try:
        # Convert number to base 10
        base10 = int(number, from_base)
    except ValueError:
        raise

    if to_base < 2 or to_base > 36:
        raise NotImplementedError

    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    sign = ''

    if base10 == 0:
        return '0'
    elif base10 < 0:
        sign = '-'
        base10 = -base10

    s = ''
    while base10 != 0:
        r = base10 % to_base
        r = int(r)
        s = digits[r] + s
        base10 //= to_base

    output_value = sign + s
    return output_value


def get_hash(img):  # перцептивный хэш

    sum_pix_color = 0
    for x in img.getdata():
        try:
            sum_pix_color += sum(list(x))
        except Exception as e:

            return None

    sred = sum_pix_color / 64

    str_hash = ''

    for x in img.getdata():
        if sum(list(x)) >= sred:
            str_hash += '1'
        else:
            str_hash += '0'

    _hash = base_convert(str_hash, 2, 16)

    return _hash


def build_structure_comments(comments):
    mapping = [['1', '1']]
    previous = ''

    for comment in comments:
        searched = False
        if not isinstance(comment, dict):
            continue
        if '/' in comment['text']:
            comments.remove(comment)
            break
        for old_id in mapping:
            if old_id[0] == str(comment['from_id']):
                comment['from_id'] = old_id[1]
                searched = True

        if searched is False:
            new_id = random.choice(akk_for_comment)['id']
            if new_id == previous:
                new_id = random.choice(akk_for_comment)['id']
            mapping.append([str(comment['from_id']), new_id])
            comment['from_id'] = new_id
            previous = new_id

        if 'reply_to_cid' in comment:
            for comment_for_search in comments:
                if isinstance(comment_for_search, dict):
                    if comment['reply_to_cid'] == comment_for_search['cid']:
                        text_split = comment['text']
                        text_split = text_split.replace('[id' + str(comment['reply_to_uid']) + '|',
                                                        '[id' + comment_for_search['from_id'] + '|')
                        massive = text_split.split('|')
                        if massive.__len__() > 1:
                            massive_name = massive[1].split('}')

                            for akk in akk_for_comment:
                                if comment_for_search['from_id'] == akk['id']:
                                    text_split = text_split.replace(massive_name[0], akk['name'])
                                    text_split += (']' + massive_name[0].split(']')[1])
                                    comment['clen_text'] = massive_name[0].split(']')[1]
                                    break

                        text_split = text_split.replace('<br>', '\n')
                        comment['text'] = text_split

                        if comment['from_id'] == comment_for_search['from_id']:
                            comment['from_id'], mapping = new_id_func(comment['from_id'], mapping)
                        break
        else:
            comment['text'] = comment['text'].replace('<br>', '\n')
            comment['clen_text'] = comment['text'].replace('<br>', '\n')

    return comments


def new_id_func(old_id_str, mapping):
    new_id_str = random.choice(akk_for_comment)['id']
    if old_id_str == new_id_str:
        new_id_str, mapping = new_id_func(old_id_str, mapping)
    else:
        mapping.append([old_id_str, new_id_str])

    return new_id_str, mapping


def init_var():
    global hash_list
    session = Session()

    groups_ = session.query(Groups).all()
    for group in groups_:
        list_groups.append([group.id_group, group.short_name])

    hash_list = session.query(Hash).all()


def main():
    # noinspection PyGlobalUndefined
    global access_token, user_id, max_count_post

    while True:
        access_token, user_id = vk.auth('+79123260552', "GiveMeUsaTank1337", "4826374",
                                        'audio,groups,friends,photos,wall,notify,messages,stats,offline')
        if access_token != '':
            break

    init_var()
    # pp = telegram.utils.request.Request(proxy_url='socks5://46.101.209.178:1080')
    # bot = telegram.Bot(token=telegram_token_news_bayanist_bot, request=pp)
    bot = Bot(telegram_token_news_bayanist_bot)
    uploader = bot.get_uploader()

    while True:

        for group_id, domain in list_groups:
            wall_record = vk_api.wall.get(owner_id=group_id, domain=domain, count='10', access_token=access_token
                                          , v='5.95')
            if wall_record is None:
                continue
            post = get_most_like_post(wall_record, domain)
            if post is None:
                continue
            else:

                photos_path = save_photo_for_post(post)

                try:
                    # status = bot.send_message(chat_id="@bayan_shop_vk", text='Хоп хэй лалалалей',
                    #                           parse_mode=telegram.ParseMode.HTML)
                    status = uploader.send_photo("@bayan_shop_vk", open(photos_path, 'rb'), request_kwargs=REQUEST_KWARGS)

                    print(status)
                except Exception as e:

                    status = None

                time_to_last_post = datetime.now()
                if status is not None:
                    utcnow = datetime.utcnow()
                    session = Session()
                    session.add_all([Post(id_post=now_post_id,
                                          timestamp=utcnow + timedelta(seconds=1),
                                          time=datetime.time(datetime.now()),
                                          id_group=domain),
                                     Hash(hash=now_img_hash,
                                          timestamp=utcnow + timedelta(seconds=1))])
                    session.commit()

                    hash_list.append(Hash(hash=now_img_hash, timestamp=utcnow + timedelta(seconds=1)))

                    time_to_sleep = 25 - ((datetime.now() - time_to_last_post).seconds / 60)

                    print('между постами рекомендуется выдержать время, в среднем ' + str(time_to_sleep) + ' минут')

                    print(datetime.now())
                    if time_to_sleep > 0:
                        time.sleep(time_to_sleep * 60)


if __name__ == '__main__':
    main()

# use token generated in first step
