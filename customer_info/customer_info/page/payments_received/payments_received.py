from __future__ import unicode_literals
import frappe
import json
from frappe.utils import flt, cstr, cint
from frappe.utils.csvutils import UnicodeWriter
import pdfkit
from customer_info.customer_info.doctype.payments_management.payments_management import set_values_in_agreement_on_submit,set_values_in_agreement_temporary 

@frappe.whitelist()
def get_payments_details(customer,from_date,to_date):
	print customer,from_date,to_date

	if customer and from_date and to_date:
		cond = "where customer = '{0}' and (payment_date BETWEEN '{1}' AND '{2}') and refund = 'No' ".format(customer,from_date,to_date)

	elif customer and from_date:
		cond = "where customer = '{0}' and payment_date >= '{1}' and refund = 'No' ".format(customer,from_date)

	elif customer and to_date:
		cond = "where customer = '{0}' and payment_date < '{1}' and refund = 'No' ".format(customer,to_date)

	elif from_date and to_date:
		cond = "where (payment_date BETWEEN '{0}' AND '{1}')  and refund = 'No' ".format(from_date,to_date)

	elif customer:
		cond = "where customer = '{0}'  and refund = 'No' ".format(customer)

	elif from_date:
		cond = "where payment_date >= '{0}' and refund = 'No' ".format(from_date)

	elif to_date:
		cond = "where payment_date <= '{0}' and refund = 'No' ".format(to_date)

	else:
		cond = " where refund = 'No' "

	
	data = frappe.db.sql("""select payment_date,customer,payoff_cond,
								rental_payment,
								format(1*late_fees,2) as late_fees,receivables,
								CASE WHEN payoff_cond = "Rental Payment" 
								THEN format(rental_payment+late_fees+receivables,2) ELSE format(total_payment_received,2) END AS total_payment_received,
								format(bank_transfer,2) as bank_transfer,format(cash,2) as cash,format(bank_card,2) as bank_card,
								balance,format(discount, 2) as discount,format(bonus,2) as bonus,concat(name,'') as refund,payments_ids
								from `tabPayments History` {0}
								order by payment_date asc """.format(cond),as_dict=1)


	total = frappe.db.sql("""select "payment_date" as payment_date,"customer" as customer,"payoff_cond" as payoff_cond,
								format(sum(rental_payment),2) as rental_payment,
								format(sum(1*late_fees),2) as late_fees,format(sum(receivables),2) as receivables,"total_payment_received" as total_payment_received,
								format(sum(bank_transfer),2) as bank_transfer,format(sum(cash),2) as cash ,format(sum(bank_card),2) as bank_card,
								format(sum(balance),2) as balance,format(sum(discount),2) as discount,format(sum(bonus),2) as bonus
								from `tabPayments History` {0}""".format(cond),as_dict=1,debug=1)
	total,"total"
	total_payment_received = []
	for i in data:
		total_payment_received.append(i['total_payment_received'].replace(",",""))
	total[0]["payment_date"] = "Total"
	total[0]["customer"] = "-"
	total[0]["payoff_cond"] = "-"
	total[0]['total_payment_received'] = "{0:.2f}".format(sum(map(float,total_payment_received)))
	return {"data":data,"total":total}

@frappe.whitelist()
def create_csv(data):
	w = UnicodeWriter()
	w = add_header(w)
	w = add_data(w, data)
	# write out response as a type csv
	frappe.response['result'] = cstr(w.getvalue())
	frappe.response['type'] = 'csv'
	frappe.response['doctype'] = "Payment Received Report"

def add_header(w):
	w.writerow(["Payment Received Report"])
	return w

def add_data(w,data):
	data = json.loads(data)
	if len(data) > 0:
		w.writerow('\n')
		w.writerow(['Payment Received'])
		w.writerow(['', 'Payment Date','Customer', 'Rental Payment','Late Fees','Receivables','Total Rental Payment','Bank Transfer','Cash','Bank Card','Balance','Discount','Bonus'])
		for i in data:
			row = ['',i['payment_date'], i['customer'], i['rental_payment'],i['late_fees'],i['receivables'],i['total_payment_received'],i['bank_transfer'],i['cash'],i['bank_card'],i['balance'],i['discount'],i['bonus']]
			w.writerow(row)	
			w.writerow(['','Payment id','Due Date','Rental Payment','Late Fees','Total'])
			for j in i['payments_ids']:
				row = ['', j['payments_id'],j['due_date'],j['rental_payment'],j['late_fees'],j['total']]
				w.writerow(row)
	return w
	 
@frappe.whitelist()
def make_refund_payment(payments_ids,ph_name):
	payments_ids = json.loads(payments_ids)
	payment_history = frappe.get_doc("Payments History",ph_name)
	customer = frappe.get_doc("Customer",payment_history.customer)
	payments_id_list = []
	agreement_list = []
	merchandise_status_list= []
	for i in payments_ids:
		frappe.db.sql("""update `tabPayments Record` set check_box = 0,pre_select_uncheck = 0,
							payment_date = "",check_box_of_submit = 0,payment_history = "",pmt="",
							total_transaction_amount = 0 
							where check_box_of_submit = 1 
							and payment_id = '{0}' """.format(i))
		payments_id_list.append(i)
		agreement_list.append(i.split("-P")[0])
	agreement_list =  list(set(agreement_list))
	if agreement_list:
		agreement_list = [x.encode('UTF8') for x in agreement_list if x]
	flag = "Make Refund"
	agreement_list.sort()

	merchandise_status = payment_history.merchandise_status
	if merchandise_status and payment_history.payment_type == "Normal Payment":
		merchandise_status_list = [x.encode('UTF8') for x in merchandise_status.split(",")[0:-1] if x]	
		merchandise_status_list.sort()
			

	for i,agreement in enumerate(agreement_list):
		customer_agreement = frappe.get_doc("Customer Agreement",agreement)
		set_values_in_agreement_on_submit(customer_agreement)
		
		if payment_history.payment_type == "Payoff Payment":
			payment_history.payoff_cond = ""
			customer_agreement.agreement_status = "Open"
			customer_agreement.merchandise_status = payment_history.merchandise_status
			customer_agreement.agreement_closing_suspending_reason = ""
			customer_agreement.save(ignore_permissions=True)

		if payment_history.payment_type == "Normal Payment" and agreement == merchandise_status_list[i].split("/")[0]:
			customer_agreement.agreement_status = "Open"
			customer_agreement.agreement_closing_suspending_reason = ""
			customer_agreement.merchandise_status = merchandise_status_list[i].split("/")[1]
			customer_agreement.agreement_closing_suspending_reason = ""  							
			customer_agreement.save(ignore_permissions=True)
		
		if payment_history.payment_type == "Normal Payment":
			customer.bonus = set_values_in_agreement_temporary(agreement,customer.bonus,flag,payments_id_list)
		customer.refund_to_customer = float(payment_history.cash) + float(payment_history.bank_card) + float(payment_history.bank_transfer) - float(payment_history.bonus) - float(payment_history.discount)
		customer.receivables = float(payment_history.rental_payment) - float(payment_history.late_fees) - float(payment_history.total_charges)
		customer.save(ignore_permissions=True)
	
	payment_history.refund = "Yes"
	payment_history.save(ignore_permissions=True)	