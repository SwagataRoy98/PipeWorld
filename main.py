import datetime
import requests
import pytz
import os
from heyoo import WhatsApp
from dotenv import load_dotenv
from flask import Flask, request, make_response, jsonify
from datetime import datetime as dt
from flask_cors import CORS, cross_origin
from flask_mail import Mail, Message
import pymysql
from pymysql import OperationalError

import re
from werkzeug.utils import secure_filename, escape
app = Flask(__name__)
load_dotenv()
ist_tz = pytz.timezone('Asia/Kolkata')
db_user = os.environ.get('CLOUD_SQL_USERNAME')
db_password = os.environ.get('CLOUD_SQL_PASSWORD')
db_name = os.environ.get('CLOUD_SQL_DATABASE_NAME')
db_connection_name = os.environ.get('CLOUD_SQL_CONNECTION_NAME')
db_host = os.environ.get('DB_HOST')
token = os.environ.get('TOKEN')
places_token = os.environ.get('PLACES_API_KEY')
print(db_connection_name)
phone_number_id = os.environ.get('PHONE_NUMBER_ID')
messenger = WhatsApp(token=token, phone_number_id=phone_number_id)
verify_token = os.environ.get('VERIFY_TOKEN')


@app.route('/', methods=["GET", "POST"])
def db_setup():
    if request.method == 'GET':
        print('Username : ' + db_user)
        cnx = connect()
        with cnx.cursor() as cursor:
            sql = 'select @@version'
            cursor.execute(sql)
            result = cursor.fetchone()

    return f"Hello World! DB Connection successful. Mysql version : {result}"


@app.route('/hook', methods=["GET", "POST"])
def hook():
    if request.method == 'GET':
        if request.args.get("hub.verify_token") == verify_token:
            print("Verified Webhook")
            response = make_response(request.args.get("hub.challenge"), 200)
            response.mimetype = "text/plain"
            return response
        return "Hello World"
    cnx = connect()
    data = request.get_json()
    print("Received webhook data: ", data)
    print('In here Part 2')
    changed_field = messenger.changed_field(data)
    if changed_field == "messages":
        print('In here Part 1')
        new_message = messenger.get_mobile(data)
        if new_message:
            print('In here Part 2')
            mobile = messenger.get_mobile(data)
            if check_blacklist(cnx, mobile):
                return 'OK', 200
            print('In here Part 3')
            name = messenger.get_name(data)
            message_type = messenger.get_message_type(data)
            cust = Customer(name, mobile)
            print("In here part 4")
            print(f"New Message; sender:{mobile} name:{name} type:{message_type}")
            if message_type == "text":
                message = messenger.get_message(data)
                print("Message: %s", message)
                if message is not None:
                    message = message.lower()
                    if message == 'hi':
                        if cust.check_cust_exist(cnx):
                            resp_id = '0A'
                            db_message_logger(cnx, message, resp_id, mobile)
                            messenger.send_message(
                                f"Hi {cust.cust_name}!!! Welcome back to Plumberwala.\n"
                                f"Please Choose from the below option which best matches your need.",
                                mobile)
                            print('Before Sending Custom Interactive Message')
                            messenger.send_message('Test Message', mobile)
                            send_custom_interactive_message(messenger, cust, '0')
                            return 'OK', 200
                        else:
                            resp_id = '0B'
                            db_message_logger(cnx, message, resp_id, mobile)
                            messenger.send_message(
                                f"Hi {cust.cust_name}!!! Welcome to Plumbing wala. "
                                f"Please provide the address to continue", mobile)
                            print('Before Sending Custom Interactive Message')

                            print('After Sending Custom Interactive Message')
                            return 'OK', 200
                    else:
                        res = get_prev_resp_id(cnx, mobile)
                        print(res[0])
                        if res is not None:
                            if re.match('^4', res[0]):
                                db_message_logger(cnx, message, '5', mobile)
                                print(res[0]+'received quantity: ' + message)
                                res = fetch_order_no(cust)
                                order = Order(phone_number=cust.phone_number, cust=cust)
                                order.update_order_line_details('order_qty', message)
                                #order_type, order_cat, order_size, order_comp
                                product = Product(product_type=res[2], product_cat=res[3], product_comp=res[5],
                                                  product_size=res[4])
                                messenger.send_message(f"Unit Price is {product.get_prod_price()} and "
                                                       f"total price for this order line will be "
                                                       f"{product.get_prod_price() * int(message)}",
                                                       mobile)
                                print('Send product message')
                                return 'OK', 200
                        else:
                            messenger.send_message(
                                f"Hi {cust.cust_name},This is an automated whatsapp chatbot, please type Hi/HI/hi/hI to"
                                f" start a conversation!", mobile)
                            return 'ok', 200
                        resp_id = '0C'
                        db_message_logger(cnx, message, resp_id, mobile)
                        messenger.send_message("Hello World", mobile)
                    send_custom_interactive_message(messenger, cust, '0')
                    print('In here Part 8')
                    return 'ok', 200
                print('In here Part 5')
                return 'OK', 200
            elif message_type == "interactive":
                message_response = messenger.get_interactive_response(data)
                intractive_type = message_response.get("type")
                message_id = message_response[intractive_type]["id"]
                message_text = message_response[intractive_type]["title"]
                print(f"Interactive Message; {message_id}: {message_text}")
                resp_id = message_id
                message = message_text
                db_message_logger(cnx, message_text, resp_id, mobile)
                send_custom_interactive_message(messenger, cust, resp_id, message)
            elif message_type == "location":
                message_location = messenger.get_location(data)
                message_latitude = message_location["latitude"]
                message_longitude = message_location["longitude"]
                print("Location received from Whatsapp Location: %s, %s, %s", message_latitude, message_longitude)
                full_address = get_places_details(message_latitude, message_longitude)
                print("Address found from API: %s", full_address)
                messenger.send_message(f"Location: {message_latitude}, {message_longitude}, \n {full_address}"
                                       f"Your address is saved with us! Thanks, You can proceed now.", mobile)
                print("Setting address for the customer with Phone Number "+cust.phone_number)
                cust.set_address(cnx, address=full_address)
                print('Address Set')
                db_message_logger(cnx, full_address, 'AD', mobile)
                print('Before sending CIM')
                send_custom_interactive_message(messenger, cust, '0')
                print('CIM sent')
            else:
                messenger.send_message(f"Oops!! Only text and interactive message supported", mobile)
        else:
            print('No New Message')
    return 'OK', 200


def connect():
    print('Trying with self load balancer')
    unix_socket = '/cloudsql/{}'.format(db_connection_name)
    cnx = pymysql.connect(user=db_user, password=db_password, unix_socket=unix_socket, db=db_name)
    print('Connected successfully to the database using host.')
    return cnx


class Customer:
    cust_name = None
    company_name = None
    phone_number = None
    cust_address = None
    cust_email = None
    cust_category = None

    def __init__(self, cust_name, phone_number, address=None):
        self.cust_name = cust_name
        self.phone_number = phone_number
        self.address = address

    def service_cust_ins(self, cnx):
        with cnx.cursor() as cursor:
            try:
                sql = "SELECT * FROM `Customer_Details` WHERE `phone_number`= %s"
                print(sql)
                cursor.execute(sql, self.mobile)
                result_one = cursor.fetchone()
                if result_one is None:
                    print("In here part 1")
                    sql = "INSERT INTO `Customer_Details` (`cust_name`, `phone_number`, `cust_address`,`InsertTS`) " \
                          "VALUES (%s, %s, %s, %s)"
                    print(sql)
                    cursor.execute(sql, (self.cust_name, self.mobile, self.address, dt.now(ist_tz).
                                         strftime('%Y-%m-%d %H:%M:%S'),))
                    cnx.commit()
                    return False
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
        return True

    def check_cust_exist(self, cnx):
        with cnx.cursor() as cursor:
            try:
                sql = "SELECT * FROM `Customer_Details` WHERE `phone_number`= %s"
                print(sql)
                cursor.execute(sql, self.phone_number)
                result_one = cursor.fetchone()
                if result_one is None:
                    print("In here part 1")
                    sql = "INSERT INTO `Customer_Details` (`cust_name`, `phone_number`,`insertts`) VALUES (%s, %s, %s)"
                    print(sql)
                    cursor.execute(sql, (self.cust_name, self.phone_number, dt.now(ist_tz).strftime('%Y-%m-%d %H:%M:%S'),))
                    cnx.commit()
                    return False
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
        return True

    def set_address(self, cnx, address=None):
        self.address = address
        with cnx.cursor() as cursor:
            try:
                sql = "UPDATE Customer_Details SET cust_address = %s where phone_number = %s"
                print(sql)
                cursor.execute(sql, (self.address, self.phone_number))
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
            return None

    def set_company_name(self, cnx, company_name=None):
        self.company_name = company_name
        with cnx.cursor() as cursor:
            try:
                sql = "UPDATE Customer_Details SET company_name = %s where phone_number = %s"
                print(sql)
                cursor.execute(sql, (self.company_name, self.phone_number))
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
            return None


def db_message_logger(cnx, message, resp_id, mobile):
    with cnx.cursor() as cursor:
        try:
            sql = "INSERT INTO `chat_log` (`phone_number`, `chat_desc`, `res_id`, `insertts`) values (%s, %s, %s, %s)"
            print(sql)
            cursor.execute(sql, (mobile, message, resp_id, dt.now(ist_tz).strftime('%Y-%m-%d %H:%M:%S'),))
            cnx.commit()

        except OperationalError as err:
            print(str(err))
            return None
        except Exception as e:
            print("Exception occurred : " + str(e))
            return None
        return None


def get_prev_resp_id(cnx, mobile):
    with cnx.cursor() as cursor:
        try:
            sql = "select `res_id`,`chat_desc` from `chat_log` where `phone_number` = %s and `log_id` = " \
                  "(select max(`log_id`) from `chat_log` where `phone_number` = %s)"
            print(sql)
            cursor.execute(sql, (mobile, mobile))
            res = cursor.fetchone()
        except OperationalError as err:
            print(str(err))
            return None
        except Exception as e:
            print("Exception occurred : " + str(e))
            return None
        return res


def check_blacklist(cnx, mobile):
    with cnx.cursor() as cursor:
        sql = "select count(*) from black_list_no where `black_phone_no` = %s"
        print(sql)
        cursor.execute(sql, mobile)
        res = cursor.fetchone()
        if res[0] == 0:
            return False
        else:
            return True


def send_custom_interactive_message(messenger, cust, resp_id, message=None):
    print('Beginning of SCIM')
    payload = None
    if resp_id == '0':
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": cust.phone_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": "Plumbing Wala"
                },
                "body": {
                    "text": "Please choose from below categories: "
                },
                "action": {
                    "button": "Options",
                    "sections": [
                        {
                            "title": "Pipes",
                            "rows": [
                                {
                                    "id": "1A",
                                    "title": "PVC Pipes"
                                },
                                {
                                    "id": "1B",
                                    "title": "CPVC Pipes"
                                },
                                {
                                    "id": "1C",
                                    "title": "Other Pipes"
                                }
                            ]
                        },
                        {
                            "title": "Fittings",
                            "rows": [
                                {
                                    "id": "1D",
                                    "title": "CP Fittings"
                                },
                                {
                                    "id": "1E",
                                    "title": "Bath Fittings"
                                },
                                {
                                    "id": "1F",
                                    "title": "Fittings"
                                }
                            ]
                        },
                        {
                            "title": "Others",
                            "rows": [
                                {
                                    "id": "1G",
                                    "title": "Water Tanks"
                                },
                                {
                                    "id": "1H",
                                    "title": "Other Plumbing Acc."
                                }
                            ]
                        }
                    ]
                }
            }
        }
    elif resp_id == '1A':
        print('')
        order = Order(phone_number=cust.phone_number, cust=cust, order_type=message)
        order.create_order_line()
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": cust.phone_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": "Plumbing Wala"
                },
                "body": {
                    "text": "Please choose from below Brands:"
                },
                "action": {
                    "button": "Options",
                    "sections": [
                        {
                            "title": "Brands",
                            "rows": [
                                {
                                    "id": "2A",
                                    "title": "Prince Pipes"
                                },
                                {
                                    "id": "2B",
                                    "title": "Supreme Pipes"
                                },
                                {
                                    "id": "2C",
                                    "title": "Other Economic Pipes"
                                }
                            ]
                        },
                    ]
                }
            }
        }
    elif resp_id == '2A':
        order = Order(phone_number=cust.phone_number, cust=cust)
        order.update_order_line_details('order_comp', message)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": cust.phone_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": "Plumbing Wala"
                },
                "body": {
                    "text": "Please choose from below types:"
                },
                "action": {
                    "button": "Options",
                    "sections": [
                        {
                            "title": "Category",
                            "rows": [
                                {
                                    "id": "3A",
                                    "title": "SWR Pipes"
                                },
                                {
                                    "id": "3B",
                                    "title": "UPVC Pipes"
                                },
                                {
                                    "id": "3C",
                                    "title": "Agriculture Pipe"
                                },
                                {
                                    "id": "3D",
                                    "title": "Gutter Pipe"
                                }
                            ]
                        },
                    ]
                }
            }
        }
    elif resp_id == '3A':
        order = Order(phone_number=cust.phone_number, cust=cust)
        order.update_order_line_details('order_cat', message)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": cust.phone_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": "Plumbing Wala"
                },
                "body": {
                    "text": "Please choose from below sizes:"
                },
                "action": {
                    "button": "Options",
                    "sections": [
                        {
                            "title": "Category",
                            "rows": [
                                {
                                    "id": "4A",
                                    "title": "110MM X 3MTR"
                                },
                                {
                                    "id": "4B",
                                    "title": "75MM X 3MTR"
                                }
                                # {
                                #     "id": "4A",
                                #     "title": "110mm X 3MTR DS"
                                # },
                                # {
                                #     "id": "4B",
                                #     "title": "75mm X 3MTR DS"
                                # }
                            ]
                        },
                    ]
                }
            }
        }

    elif resp_id == '4A' or resp_id == '4B' or resp_id == '4C' or resp_id == '4D':
        order = Order(phone_number=cust.phone_number, cust=cust)
        order.update_order_line_details('order_size', message)
        messenger.send_message("Please Enter the Quantity", cust.phone_number)
        print(resp_id)
    print('Payload Prepared in send custom interactive message')
    requests.post(messenger.url, headers=messenger.headers, json=payload)
    print('Request sent in send custom interactive message')
    return None


def fetch_order_no(cust):
    cnx = connect()
    with cnx.cursor() as cursor:
        try:
            sql = "SELECT order_no, order_id, order_type, order_cat, order_size, order_comp  FROM `order_log` " \
                  "WHERE phone_number = %s AND order_id = (select max(order_id) from `order_log` where " \
                  "phone_number = %s and order_stat = 'A')"
            print(sql)
            cursor.execute(sql, (cust.phone_number, cust.phone_number))
            result = cursor.fetchone()
            if result is None:
                result = [get_order_no(cnx), '01']
        except OperationalError as err:
            print(str(err))
            return None
        except Exception as e:
            print("Exception occurred : " + str(e))
            return None
        return result


def get_order_no(cnx):
    with cnx.cursor() as cursor:
        try:
            sql = f"select max(order_id) from order_log "
            print(sql)
            cursor.execute(sql)
            result = cursor.fetchone()
            print(type(result[0]))
            if result[0] is not None:
                order_no = 100000 + int(result[0]) + 1
                order_no = 'ON' + str(order_no)
            else:
                order_no = 'ON100001'
        except OperationalError as err:
            print(str(err))
            return None
        except Exception as e:
            print("Exception occurred : " + str(e))
            return None
        return order_no


class Order:

    order_no = None
    invoice_no = None
    phone_number = None
    cust = None
    order_type = None
    # def __init__(self, phone_number):
    #     self.phone_number = phone_number
    #     cnx = connect()
    #     with cnx.cursor() as cursor:
    #         sql = f"select "

    def __init__(self, phone_number, cust, order_type=None):
        self.phone_number = phone_number
        self.order_type = order_type
        self.cust = cust
        cnx = connect()
        prev_order = fetch_order_no(self.cust)
        if prev_order is None:
            self.order_no = get_order_no(cnx)
        else:
            self.order_no = prev_order[0]
        self.invoice_no = self.order_no+'_' + str(prev_order[1])

    def calculate_grand_total(self):
        cnx = connect()
        with cnx.cursor() as cursor:
            try:
                sql = f"select order_type, order_comp, order_cat, order_sub_cat, order_size from order_log " \
                      f"where order_stat = 'C' and phone_number = {self.phone_number}"
                print(sql)
                cursor.execute(sql)
                orders = cursor.fetchall()
                print(type(orders))
                print(orders)
                total_price = 0
                for order in orders:
                    product = Product(product_type=order[0], product_cat=order[2], product_comp=order[1],
                                      product_sub_cat=order[3], product_size=order[4])
                    total_price = total_price + product.get_prod_price()
                return total_price
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None

    def create_order_line(self):
        cnx = connect()
        with cnx.cursor() as cursor:
            try:
                sql = f"insert into `order_log` (`order_no`,`invoice_no`,`phone_number`, `order_type`, `order_stat`) " \
                      f"values ('{self.order_no}','{self.invoice_no}','{self.phone_number}', '{self.order_type}', 'A')"
                print(sql)
                cursor.execute(sql)
                cnx.commit()
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
        return None

    def update_order_line_details(self, col_name, col_val):
        cnx = connect()
        with cnx.cursor() as cursor:
            try:
                sql = f"select max(order_id) from `order_log` where phone_number = '{self.phone_number}' "\
                        f"and order_stat = 'A'"
                cursor.execute(sql)
                result = cursor.fetchone()
                sql = f"update order_log set {col_name} = '{col_val}' where " \
                      f"order_id = {result[0]}"
                # sql = f"UPDATE order_log AS ol1 "
                # f"JOIN ( "
                # f"    SELECT MAX(order_id) AS max_order_id "
                # f"    FROM order_log "
                # f"    WHERE phone_number = '{self.phone_number}' AND order_stat = 'A' "
                # f") AS ol2 ON ol1.order_id = ol2.max_order_id "
                # f"SET {col_name} = '{col_val}'"
                print(sql)
                cursor.execute(sql)
                cnx.commit()
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
        return None

    def confirm_order(self):
        cnx = connect()
        with cnx.cursor() as cursor:
            try:
                sql = f"update `order_log` set order_stat = 'F' where phone_number = '{self.phone_number}' and " \
                      f"order_stat = 'C'"
                print(sql)
                cursor.execute(sql)
                cnx.commit()
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
        return None


class Product:
    product_type = None
    product_cat = None
    product_comp = None
    product_sub_cat = None
    product_size = None

    def __init__(self, product_type, product_cat, product_comp, product_size):
        self.product_type = product_type
        self.product_cat = product_cat
        self.product_comp = product_comp
        self.product_size = product_size

    def get_prod_price(self):
        cnx = connect()
        with cnx.cursor() as cursor:
            try:
                sql = f"select prod_price from `prod_table` where prod_type = '{self.product_type}' " \
                      f"and prod_cat = '{self.product_cat}' " \
                      f"and prod_comp = '{self.product_comp}' " \
                      f"and prod_size = '{self.product_size}' "
                print(sql)
                cursor.execute(sql)
                result = cursor.fetchone()
                print(type(result))
                print(result[0])
                return result[0]
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None


def get_places_details(latitude, longitude):
    nearby_search_url = f"https://maps.googleapis.com/maps/api/geocode/json?key={places_token}&latlng={latitude}," \
                        f"{longitude}"
    response = requests.get(nearby_search_url)
    data = response.json()
    formatted_address = data["results"][0]["formatted_address"]
    return formatted_address


if __name__ == '__main__':
    app.run()
