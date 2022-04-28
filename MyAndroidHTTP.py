import threading
import socket
import datetime
import base64
from urllib.parse import unquote
from urllib.parse import quote
import os
from copy import deepcopy
import time


# Config Start
address = ''
port = 8081
listen_num = 100
download_dir = "./file/"
upload_dir = "./upload/"
max_length = 128 * 1024 * 1024 # default 16 M
time_out = 600 # default 50 seconds


# You can change ther headers here
def get_res(content, status, mime_type, charset, content_len=-1, extra_headers=""):
    if content_len == -1:
        content_len = str(len(content.encode(charset)))
    date = datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')

    return  ("HTTP/1.1 " + status + "\r\n" +
            "Content-Length: " + str(content_len) + "\r\n" +
            "Cache-directive: no-store\r\n" +
            "Connection: Close\r\n" +
            "Date: " + date + "\r\n" +
            "Server: lyc8503PythonHTTP\r\n" +
            "Content-Type: " + mime_type + "; charset=" + charset + "\r\n" + extra_headers +"\r\n" + content).encode(charset)
# Config End


try:
    os.mkdir(download_dir)
except:
    pass

try:
    os.mkdir(upload_dir)
except:
    pass
os.chdir(download_dir)


#  ***** HTTP Server Part Start *****
# Create server socket
server_sock = socket.socket()
server_sock.bind((address, port))
server_sock.listen(listen_num)


# Parse HTTP headers
def parse_input(input):
    back = deepcopy(input)
    input = input.decode("utf-8", errors="ignore")
    result = {}
    if input[0:3].lower() == "get":
        result["method"] = "GET"
        input = input[4:]
    elif input[0:4].lower() == "post":
        result["method"] = "POST"
        input = input[5:]
    else:
        result["method"] = "unknown"
        return result

    result['params'] = {}
    for i in range(0, 1000):
        if input[i] == " ":
            temp = input[:i]
            for i2 in range(0, len(temp)):
                if temp[i2] == "?":
                    param_str = temp[i2 + 1:]
                    result["path"] = temp[:i2]
                    params = param_str.split("&")
                    for param in params:
                        param = param.split("=")
                        if len(param) == 2:
                            result['params'][param[0]] = unquote(param[1])
                    break
            else:
                result["path"] = temp
            input = input[i + 1:]
            break
    else:
        return None

    if result['method'] == 'POST':
        result['data'] = back[back.find(b'\r\n\r\n'):]

    # Get headers
    headers_str = ""
    for i in range(0, len(input)):
        if input[i: i + 4] == "\r\n\r\n":
            headers_str = input[0:i]
            break

    headers = {}
    headers_str = headers_str.split("\r\n")
    for i in headers_str:
        i = i.split(":")
        if len(i) <= 1:
            continue
        headers[i[0]] = i[1].lstrip()
    result['headers'] = headers

    return result


context = []


def bind_context(path, func):
    context.append([path, func, "func"])


def bind_html(path, html):
    context.append([path, html, "html"])


# Handle a request
def handle(sock):
    global max_length, time_out
    content_length = -666
    header = ''
    temp_ok = False
    try:
        res = b''
        sock.settimeout(0.5)

        timeout_counter = 0
        start_time = time.time()
        while True:
            try:
                temp = sock.recv(81920)
                res += temp
                timeout_counter = 0
            except Exception as e:
                timeout_counter += 1

            if res[-4:] == b'\r\n\r\n' and res[:3].decode('utf-8').lower() == 'get':
                break

            if not temp_ok:
                header = res[:res.find(b'\r\n\r\n')].decode('utf-8').lower()
                if len(res) > 200 * 1024:
                    sock.sendall(get_res("HTTP Status 400 Bad Request: Headers too long", "400 Bad Request", "text/plain", "utf-8"))
                    sock.close()
                    return
                if res[:4].decode('utf-8').lower() == 'post' and header.find('content-length') != -1:
                    content_length = int(header[header.find('content-length:') + 15:header[header.find('content-length:'):].find('\r\n') + header.find('content-length:')])
                    temp_ok = True

            if temp_ok:
                if len(res) - res.find(b'\r\n\r\n') - 4 == content_length:
                    break

            if not temp_ok:
                if timeout_counter > 20: # 10s 没有数据直接结束 以防止没有 Content-Length 的情况
                    break

            if time.time() - start_time > time_out:
                print("HTTP time out.")
                del res
                sock.setblocking(True)
                sock.sendall(get_res("TIME OUT.", "500 Internal Server Error", "text/plain", "utf-8"))
                sock.close()
                return

            if len(res) > max_length + 200 * 1024: # 补偿Headers
                del res
                print("Max data length exceeded.")
                sock.setblocking(True)
                sock.sendall(get_res("MAX DATA LENGTH EXCEEDED.", "400 Bad Request", "text/plain", "utf-8"))
                sock.close()
                return

        sock.setblocking(True)

        res = parse_input(res)
        try:
            print(res['method'] + ' ' + res['path'])
        except:
            pass

        # Bad Request
        if res is None:
            sock.sendall(get_res("HTTP Status 400 Bad Request", "400 Bad Request", "text/plain", "utf-8"))
            sock.close()
            return

        # Unknown method
        if res["method"] == "unknown":
            sock.sendall(get_res("HTTP Status 405 Method Not Allowed", "405 Method Not Allowed", "text/plain", "utf-8"))
            sock.close()
            return

        for i in context:
            if i[0] == res["path"]:
                if i[2] == "html":
                    sock.sendall(get_res(i[1], "200 OK", "text/html", "utf-8"))
                    sock.close()
                    return
                if i[2] == "func":
                    i[1](sock, res)
                    return

        sock.sendall(get_res("HTTP Status 404 Not Found", "404 Not Found", "text/plain", "utf-8"))
        sock.close()
    except Exception as e:
        print(e)
        sock.sendall(get_res("HTTP Status 500 Internal Server Error\nDetailed Info: " + str(e), "500 Internal Server Error", "text/plain", "utf-8"))
        sock.close()

# 密码认证
def auth(sock, headers, username, password, msg):
    try:
        pass_res = headers['Authorization']
        if (pass_res[0:6]).lower() != "basic ":
            sock.sendall(get_res("HTTP Status 401 Unauthorized", "401 Unauthorized", "text/plain", "utf-8", extra_headers='WWW-Authenticate: Basic realm="%s"\r\n' % msg))
            sock.close()
            return False
        pass_get = base64.b64decode(pass_res[6:]).decode("utf-8").split(":")
        if username == pass_get[0] and password == pass_get[1]:
            return True
        else:
            sock.sendall(get_res("HTTP Status 401 Unauthorized", "401 Unauthorized", "text/plain", "utf-8", extra_headers='WWW-Authenticate: Basic realm="%s"\r\n' % msg))
            sock.close()
            return False

    except Exception as e:
        print(e)
        sock.sendall(get_res("HTTP Status 401 Unauthorized", "401 Unauthorized", "text/plain", "utf-8", extra_headers='WWW-Authenticate: Basic realm="%s"\r\n' % msg))
        sock.close()
        return False


# Multiple threads to handle clients
class HandleThread(threading.Thread):
    def __init__(self, sk):
        super().__init__()
        print("New Client Connected: " + str(sk))
        self.sk = sk
        self.start()

    def run(self):
        handle(self.sk)


# Listen on the server socket
class ListenThread(threading.Thread):
    def __init__(self, server_socket):
        super().__init__()
        print("Start Listening...")
        self.ssk = server_socket
        self.start()

    def run(self):
        while True:
            try:
                sock, addr = self.ssk.accept()
                HandleThread(sock)
            except Exception as e:
                print(e)


# ***** Modify Pages *****

# Upload & Download
def upload(sock, res):
    if not auth(sock, res['headers'], 'lyc8503', '@##>^^^^', 'Upload password'):
        return
    try:
        con_type = ""
        for i in res['headers']:
            if i.lower() == "content-type":
                con_type = res['headers'][i]
        if con_type == "" or con_type.find("multipart/form-data") == -1 :
            raise Exception()
        boundary = ""
        start_index = 99999999
        end_index = 99999999
        for i in range(0, len(con_type)):
            if con_type[i: i + 9] == "boundary=":
                start_index = i + 9
                for i2 in range(i + 9, len(con_type)):
                    try:
                        if con_type[i2] == ";":
                            end_index = i2
                            break
                    except Exception as e:
                        end_index = len(con_type)
                        break
        boundary = con_type[start_index:end_index].strip()
        if boundary == '':
            raise Exception()
    except Exception as e:
        global max_length, time_out
        sock.sendall(get_res("""
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<title>上传文件</title>
</head>
<body>
<p><strong>上传文件</strong></p>
上传时长限制 %s 秒 上传大小限制 %s MB<br /><br />
<form action="/upload" method="post" enctype="multipart/form-data" name="form1" id="form1">
  <label>
  <input type="file" name="file" />
  </label>
  <p>
    <label>
    <input type="submit" name="Submit" value="提交" />
    </label>
  </p>
</form>
<p>&nbsp;</p>
</body>
</html>
""" % (str(time_out), str(max_length / 1024 / 1024)), "200 OK", "text/html", "utf-8"))
        sock.close()
        return
    print("Uploading...")

    boundary = boundary.encode('utf-8')
    end = res['data'].find(b'--' + boundary + b'--')
    if end == -1:
        sock.sendall(get_res("Corrupted file. Please retry.", "500 Internal Server Error", "text/plain", "utf-8"))
        sock.close()
        return

    response = ''
    objects = res['data'].split(b'--' + boundary)
    global upload_dir
    for i in objects:
        if i.find(b'\r\n\r\n') != -1:
            start_part = i[:i.find(b'\r\n\r\n')]
            filename_index = start_part.find(b'filename="')
            if filename_index != -1:
                # 获取文件名
                filename = start_part[filename_index + 10:start_part[filename_index + 10:].find(b'"') + filename_index + 10]
                response += '正在处理文件%s... ' % filename.decode('utf-8')
                print(filename)
                if filename.find(b'/') != -1 or filename.find(b'\\') != -1 or filename.find(b'*') != -1 or filename.find(b'?') != -1:
                    response += 'Error 非法文件名'
                try:
                    content = i[i.find(b'\r\n\r\n') + 4:-2]
                    f = open(upload_dir + filename.decode('utf-8'), 'wb')
                    f.write(content)
                    f.close()
                except Exception as e:
                    print(e)
                    response += "Error %s\n" % str(e)
                    continue
                response += "OK\n"
    response += '文件上传完成!'
    sock.sendall(get_res(response, "200 OK", "text/plain", "utf-8"))
    sock.close()

def download(sock, res):
    try:
        file_name = unquote(res['params']['name'])
    except Exception as e:
        sock.sendall(get_res("""
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<title>文件下载</title>
</head>
<body>
<p><strong>文件下载</strong></p>
<form id="filedownload_form" name="filedownload_form" method="get" action="./download">
  <label>文件名:
  <input type="text" name="name" accesskey="name" />
  </label>
  <label>
  <input type="submit" name="Submit" value="提交" accesskey="submit" />
  </label>
</form>
<p>&nbsp;</p>
</body>
</html>
""", "200 OK", "text/html", "utf-8"))
        sock.close()
        return
    try:
        f = open(file_name, "rb")
    except Exception as e:
        print(e)
        sock.sendall(get_res("File does not exist. Please retry.", "200 OK", "text/plain", "utf-8"))
        sock.close()
        return

    print("Downloading... " + file_name)
    sock.sendall(get_res("", "200 OK", "application/octet-stream", "utf-8", content_len=os.path.getsize(file_name), extra_headers="Content-Disposition: attachment;filename=" + quote(file_name) + "\r\n"))

    try:
        while True:
            content = f.read(81920)
            if content == b'':
                break
            sock.sendall(content)
    except Exception as e:
        print(e)
    f.close()
    sock.close()
    return


bind_context("/upload", upload)
bind_context("/download", download)

# Root handle
content = ""
public_links = []
private_links = []


def set_content(html):
    global content
    content = html


def add_public_link(text, dest):
    global public_links
    public_links.append([text, dest])


def add_private_link(text, dest):
    global private_links
    private_links.append([text, dest])


def show_main_page(sock, response):
    main_page = """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<title>lyc8503's Website</title>
<style type="text/css">
<!--
.STYLE1 {
	font-size: x-large;
	font-weight: bold;
}
.STYLE2 {font-size: large}
.STYLE3 {font-size: small}
.STYLE4 {font-size: large; font-weight: bold; }
-->
</style>
</head>

<body>
<p><span class="STYLE1">Lyc8503's Website on Android</span> <span class="STYLE3">Powered by lyc8503 Python HTTP Server </span></p>
<p class="STYLE2">Made by lyc8503 :P </p>
<br />
%s
<p class="STYLE2">&nbsp;</p>
<p class="STYLE4">Public links</p>
%s
<p class="STYLE2">&nbsp;</p>
<p class="STYLE2"><strong>Private links (ps: 以下的内容需要身份验证)</strong></p>
%s
</body>
</html>
"""
    global public_links, private_links, content
    pub = ""
    pri = ""
    if public_links:
        for i in public_links:
            pub += "<a href=" + i[1] + ">" + i[0] + "</a><br /><br />\n"
    else:
        pub = "<p>No content</p>"

    if private_links:
        for i in private_links:
            pri += "<a href=" + i[1] + ">" + i[0] + "</a><br /><br />\n"
    else:
        pri = "<p>No content</p>"
    
    sock.sendall(get_res(main_page % (content, pub, pri), "200 OK", "text/html", "utf-8"))
    sock.close()
    print("Main page OK.")


add_private_link("上传文件", "/upload")
bind_context("/", show_main_page)
set_content("""
<p>这里是我的安卓网站~</p>
<p>不出意外<del>(e.g. 在家走路绊到Wifi网线)</del> 这个网站会全时段开放</p>
<p>这次从HTTP协议开始都是我自己实现的! (´ｰ∀ｰ`) <del>(当然因为页面是自己写的,没有那么好看 :P)</del></p>
<p>会把一些杂七杂八的东西全部丢上来...</p>
<p>就可以从网页上直接调用我的一些东西辣 :)</p>
""")


# Server Status
def show_status(sock, res):
    global server_sock
    stat = """
<p>Server: <b>Python HTTP Server implemented by lyc8503</b></p>
<p>Server Status: Running on <ins>%s</ins></p>
<p>Date: %s</p>
"""
    sock.sendall(get_res(stat % (server_sock.getsockname()[0] + ":" + str(server_sock.getsockname()[1]), datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")), "200 OK", "text/html", "utf-8"))
    sock.close()


bind_context("/status", show_status)
add_public_link("服务器状态", "/status")

bind_html("/incich_school_utilities", """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<title>紫橙科技班牌实用工具</title>
<style type="text/css">
<!--
.STYLE1 {
	font-size: 16px;
	font-weight: bold;
}
-->
</style>
</head>

<body>
<p class="STYLE1">紫橙科技班牌实用工具 Windows 版本发布</p>
<p>**功能&amp;介绍**(重要)可以在我的Github账号上看到: <a href="https://github.com/lyc8503/IncichSchoolUtilities">https://github.com/lyc8503/IncichSchoolUtilities</a></p>
<p>能看到这个页面的应该都认识我了...功能你应该也知道了?(还不了解的自己点上面的链接)</p>
<p>安装过程中需要用到的<a href="/download?name=code.txt">邀请码</a>的站内链接</p>
<p>简单介绍一下安装过程:</p>
1.下载文件<br />
<a href="https://github.com/lyc8503/IncichSchoolUtilities/tree/master/WindowsBuild">Windows(Github)</a>
<br/>
<a href="/download?name=紫橙科技班牌实用工具.zip">本站下载</a><br />
<a href="https://pan.baidu.com/s/1hOb_XjzyCIGBDqn8SlWBZA">百度网盘</a><br/><br />
2.初始化程序(第一次启动)<br />
  解压下载到的文件<br />
  执行其中的&quot;初始化程序.exe&quot;<br />
  对照<a href="https://github.com/lyc8503/IncichSchoolUtilities/blob/master/src/%E9%82%80%E8%AF%B7%E7%A0%81.txt">邀请码列表</a>找到你所在学校班级邀请码(更新到2018-11,若没有你所在班级请与我联系)<br />
  填写邀请码与真实姓名<br />
  完成!<br /><br />
3.主程序<br />
  以后每一次启动只需要双击运行&quot;主程序.exe&quot;<br />
  (需要保持电脑开启才能在学校中使用)
</body>

</html>

""")
add_public_link("班牌实用工具Windows版本发布", "/incich_school_utilities")


# Server Start
print("Lyc8503's Android Website HTTP")
ListenThread(server_sock)
