from odoo import api, fields, models, _
from odoo.tools.safe_eval import safe_eval
import logging
import datetime
import io
import base64
import pytz
import re
from pytz import timezone, UTC
from odoo.exceptions import ValidationError
from base64 import encodebytes
import xlsxwriter
from io import BytesIO

_logger = logging.getLogger(__name__)


class PosAnnexWizard(models.TransientModel):
    _name = 'pos.annex.wizard'
    _description = 'POS Annex Report Wizard'

    pos_id = fields.Many2one('pos.config', string="POS Configuration")

    report_type = fields.Selection([
        ('e-1', 'E-1:BIR SALES SUMMARY REPORT'),
        ('e-2', 'E-2:Senior Citizen Sales Book/Report (SC)'),
        ('e-3', 'E-3:Persons with Disability Sales Book/Report (PWD)'),
        ('e-4', 'E-4:National Athletes and Coaches Sales Book/Report (NAAC)'),
        ('e-5', 'E-5:Solo Parent Sales Book/Report (SP)')
    ], string="Report Type", required=True)

    # --- Default Date Logic ---

    def _default_date_from(self):
        """
        Start of current day in user's timezone → converted to naive UTC.
        """
        tz = self.env.user.tz or 'UTC'
        user_tz = timezone(tz)

        now_utc = datetime.datetime.now(UTC)
        now_user = now_utc.astimezone(user_tz)

        start_user = now_user.replace(hour=0, minute=0, second=0, microsecond=0)

        # Convert back to UTC and strip tz info
        start_utc = start_user.astimezone(UTC)
        return start_utc.replace(tzinfo=None)

    def _default_date_to(self):
        """
        End of current day in user's timezone → converted to naive UTC.
        """
        tz = self.env.user.tz or 'UTC'
        user_tz = timezone(tz)

        now_utc = datetime.datetime.now(UTC)
        now_user = now_utc.astimezone(user_tz)

        end_user = now_user.replace(hour=23, minute=59, second=59, microsecond=999999)

        end_utc = end_user.astimezone(UTC)
        return end_utc.replace(tzinfo=None)

    date_from = fields.Datetime(string="Start Date", required=True, default=_default_date_from)
    date_to = fields.Datetime(string="End Date", required=True, default=_default_date_to)

    # --- Default Date Validation Logic ---

    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        """Ensure date_to is not earlier than date_from"""
        for record in self:
            if record.date_from and record.date_to:
                if record.date_to < record.date_from:
                    raise ValidationError(
                        _("End Date cannot be earlier than Start Date.")
                    )

    @api.constrains('date_from', 'date_to')
    def _check_date_future(self):
        """Prevent selecting future dates (date only, not time)"""
        for record in self:
            employee_timezone = pytz.timezone(self.env.user.tz or 'UTC')
            now_datetime = fields.Datetime.now().astimezone(employee_timezone)
            if record.date_from and record.date_from.date() > now_datetime.date():
                raise ValidationError(
                    _("Start Date cannot be in the future.")
                )

            if record.date_to and record.date_to.date() > now_datetime.date():
                raise ValidationError(
                    _("End Date cannot be in the future.")
                )

    @api.constrains('date_from', 'date_to')
    def _check_date_range_limit(self):
        """Optional: Limit the date range to prevent performance issues"""
        for record in self:
            if record.date_from and record.date_to:
                delta = record.date_to - record.date_from
                if delta.days > 365:  # Adjust the limit as needed
                    raise ValidationError(
                        _("Date range cannot exceed 365 days.")
                    )

    @api.onchange('date_from')
    def _onchange_date_from(self):
        """Auto-adjust date_to if it becomes invalid"""
        if self.date_from and self.date_to and self.date_to < self.date_from:
            self.date_to = self.date_from

    @api.onchange('pos_id')
    def _onchange_pos_id(self):
        """You can add logic here when POS configuration changes"""
        # Example: Set default dates based on POS session dates
        pass

    # ----------------------------------------------------
    # BUTTON ACTIONS & INJECTED LOGIC
    # ----------------------------------------------------

    def action_preview_report(self):
        return self.action_generate_report()

    def action_generate_report(self):
        self.ensure_one()
        attachment_id = False

        if self.report_type == 'e-1':
            attachment_id = self._logic_e1()
        elif self.report_type == 'e-2':
            attachment_id = self._logic_e2()
        elif self.report_type == 'e-3':
            attachment_id = self._logic_e3()
        elif self.report_type == 'e-4':
            attachment_id = self._logic_e4()
        elif self.report_type == 'e-5':
            attachment_id = self._logic_e5()

        if attachment_id:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment_id}?download=true',
                'target': 'new',
            }
        return {'type': 'ir.actions.act_window_close'}

    def _logic_e1(self):

        pos_id = self.pos_id
        date_from = self.date_from
        date_to = self.date_to

        # Timezone conversion logic
        user_tz = self.env.user.tz or 'UTC'
        user_timezone = timezone(user_tz)
        utc_timezone = pytz.UTC

        date_from_utc = user_timezone.localize(date_from.replace(tzinfo=None)).astimezone(
            utc_timezone) if date_from else fields.Datetime.now()
        date_to_utc = user_timezone.localize(date_to.replace(tzinfo=None)).astimezone(
            utc_timezone) if date_to else fields.Datetime.now()

        # Sessions search
        session_domain = [
            ('config_id', '=', pos_id.id),
            ('start_at', '>=', date_from_utc),
            ('stop_at', '<=', date_to_utc),
            ('state', '=', 'closed')
        ]
        sessions = self.env['pos.session'].search(session_domain, order='id asc')

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('E-1')

        title = self._make_format(workbook, size=14)
        label = workbook.add_format({'bold': True, 'font_size': 10})
        center = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        num_fmt = workbook.add_format({'border': 1, 'align': 'right', 'num_format': '#,##0.00', 'font_size': 9})
        header_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'font_size': 10
        })

        colors = {
            'gray': '#A6A6A6', 'blue': '#00B0F0', 'yellow': '#FFFF00',
            'orange': '#FFC000', 'green': '#92D050', 'light_gray': '#BFBFBF'
        }
        fmt = {}
        for k, v in colors.items():
            f = self._make_format(workbook, v)
            f.set_bold(False)
            fmt[k] = f

        # ---- ALL COLUMN WIDTH
        sheet.set_column('A:AF', 12)
        sheet.set_column('F:F', 18)
        sheet.set_column('S:S', 18)

        # ---- Dynamic Header (P:X columns)
        raw_header = self.pos_id.receipt_header or ""
        header_lines = [self.pos_id.name] + [
            line.strip() for line in raw_header.split('\n') if line.strip()
        ]
        for i, text in enumerate(header_lines, start=1):
            sheet.merge_range(f'P{i}:X{i}', text, header_format)

        # ANNEX "E-1" BOX — always row 2-3
        sheet.merge_range('AD2:AF3', 'ANNEX "E-1"', workbook.add_format({
            'bold': True, 'border': 2, 'align': 'center', 'valign': 'vcenter', 'font_size': 14
        }))

        # ---- Meta Data (dynamic row based on header size)
        next_row = len(header_lines) + 1

        software_info = f"{self.pos_id.name_software or ''} {self.pos_id.version_software or ''}"
        release_info = f"{self.pos_id.no_release or ''} {self.pos_id.release_date.strftime('%m-%d-%Y') if self.pos_id.release_date else ''}"

        tz = self.env.user.tz or 'UTC'
        user_tz = pytz.timezone(tz)
        local_date_from = pytz.UTC.localize(self.date_from).astimezone(user_tz)
        local_date_to = pytz.UTC.localize(self.date_to).astimezone(user_tz)
        date_from_str = local_date_from.strftime('%m/%d/%Y')
        date_to_str = local_date_to.strftime('%m/%d/%Y')

        meta = [
            (f'A{next_row}', f"Software Info: {software_info}  {release_info}"),
            (f'R{next_row}', f"Register ID: {self.pos_id.register_id_char or ''}"),
            (f'A{next_row + 1}', f"Serial No: {self.pos_id.x_serial_number or ''}"),
            (f'R{next_row + 1}', f"Date Range: {date_from_str} - {date_to_str}"),
            (f'A{next_row + 2}', f"Machine Identification Number: {self.pos_id.x_min_number or ''}"),
            (f'R{next_row + 2}', f"User ID: {self.env.user.name}"),
            (f'A{next_row + 3}', f"Branch: {self.pos_id.branch_name or self.pos_id.name}"),
            (f'R{next_row + 3}', f"Permit Number: {self.pos_id.permit_no or ''}"),
        ]
        for cell, txt in meta:
            sheet.write(cell, txt)

        # ---- Report Title
        title_row = next_row + 5
        sheet.merge_range(f'A{title_row}:AI{title_row}', 'BIR SALES SUMMARY REPORT', title)

        # ---- Table Header row heights (dynamic)
        h1 = title_row + 1
        h2 = title_row + 2
        h3 = title_row + 3
        h4 = title_row + 4  # data starts here

        sheet.set_row(h1 - 1, 35)
        sheet.set_row(h2 - 1, 35)
        sheet.set_row(h3 - 1, 45)
        sheet.set_row(h4 - 1, 25)

        # ---- TABLE HEADER
        sheet.merge_range(f'A{h1}:A{h3}', 'Date', fmt['gray'])
        sheet.merge_range(f'B{h1}:B{h3}', 'Beginning SI No.', fmt['gray'])
        sheet.merge_range(f'C{h1}:C{h3}', 'Ending SI No.', fmt['gray'])
        sheet.merge_range(f'D{h1}:D{h3}', 'Grand Accum. Sales Ending Balance\nPresent Accumulated Sales', fmt['blue'])
        sheet.merge_range(f'E{h1}:E{h3}', 'Grand Accum. Beg. Balance\nPrevious Accumulated Sales', fmt['blue'])
        sheet.merge_range(f'F{h1}:F{h3}', 'Sales Issued w/ Manual SI/OR \n(per RR 16-2018)', fmt['blue'])
        sheet.merge_range(f'G{h1}:G{h3}', 'Gross Sales for the Day', fmt['blue'])

        # VAT
        sheet.merge_range(f'H{h1}:H{h3}', 'VATable Sales', fmt['yellow'])
        sheet.merge_range(f'I{h1}:I{h3}', 'VAT Amount', fmt['yellow'])
        sheet.merge_range(f'J{h1}:J{h3}', 'VAT-Exempt Sales', fmt['yellow'])
        sheet.merge_range(f'K{h1}:K{h3}', 'Zero-Rated Sales', fmt['yellow'])

        # Deductions & Discounts
        sheet.merge_range(f'L{h1}:T{h1}', 'Deductions', fmt['orange'])
        sheet.merge_range(f'L{h2}:Q{h2}', 'Discount', fmt['orange'])
        sheet.write(f'L{h3}', 'SC', fmt['orange'])
        sheet.write(f'M{h3}', 'PWD', fmt['orange'])
        sheet.write(f'N{h3}', 'NAAC', fmt['orange'])
        sheet.write(f'O{h3}', 'Solo Parent', fmt['orange'])
        sheet.write(f'P{h3}', 'MV', fmt['orange'])
        sheet.write(f'Q{h3}', 'Others', fmt['orange'])
        sheet.merge_range(f'R{h2}:R{h3}', 'Returns', fmt['orange'])
        sheet.merge_range(f'S{h2}:S{h3}', 'Voids', fmt['orange'])
        sheet.merge_range(f'T{h2}:T{h3}', 'Total Deductions', fmt['orange'])

        # Adjustment on VAT
        sheet.merge_range(f'U{h1}:AB{h1}', 'Adjustment on VAT', fmt['green'])
        sheet.merge_range(f'U{h2}:Y{h2}', 'Discount', fmt['green'])
        sheet.write(f'U{h3}', 'SC', fmt['green'])
        sheet.write(f'V{h3}', 'PWD', fmt['green'])
        sheet.write(f'W{h3}', 'Solo Parent', fmt['green'])
        sheet.write(f'X{h3}', 'MV', fmt['green'])
        sheet.write(f'Y{h3}', 'Others', fmt['green'])
        sheet.merge_range(f'Z{h2}:Z{h3}', 'VAT on Returns', fmt['green'])
        sheet.merge_range(f'AA{h2}:AA{h3}', 'Others', fmt['green'])
        sheet.merge_range(f'AB{h2}:AB{h3}', 'Total VAT Adjustment', fmt['green'])

        sheet.merge_range(f'AC{h1}:AC{h3}', 'VAT Payable', fmt['light_gray'])
        sheet.merge_range(f'AD{h1}:AD{h3}', 'Net Sales', fmt['light_gray'])
        sheet.merge_range(f'AE{h1}:AE{h3}', 'Sales Overrun / Overflow', fmt['light_gray'])
        sheet.merge_range(f'AF{h1}:AF{h3}', 'Total Income', fmt['light_gray'])
        sheet.merge_range(f'AG{h1}:AG{h3}', 'Reset Counter', fmt['light_gray'])
        sheet.merge_range(f'AH{h1}:AH{h3}', 'Z-Counter', fmt['light_gray'])
        sheet.merge_range(f'AI{h1}:AI{h3}', 'Remarks', fmt['light_gray'])

        # ---- Data Rows
        row = h4 - 1  # 0-indexed
        for session in sessions:
            data = {'pos_session_id': [session.id], 'sh_preview_mode_on': True}
            report_obj = self.env['report.sh_pos_all_in_one_retail.new_sh_pos_z_report_doc']
            vals = report_obj._get_report_values(None, data)

            if vals.get('session_detail'):
                sd = vals['session_detail'][0]

                other_discount_exempt_tax = 0
                domain = [
                    ('state', 'in', ['paid', 'done', 'invoiced']),
                    ('date_order', '>=', date_from_utc),
                    ('date_order', '<=', date_to_utc)
                ]

                if pos_id:
                    domain.append(('config_id', '=', pos_id.id))


                pos_orders = self.env['pos.order'].search(domain, order='date_order asc')
                for order in pos_orders:
                        for line in order.lines:
                            if line.applied_discount_code in ['senior', 'pwd', 'spic','medal']:
                                pass
                            else:
                                if line.discount_vat_treatment == 'vat_exempt':
                                    company_domain = self.env['account.tax']._check_company_domain(
                                        line.order_id.company_id)
                                    tax_ids = line.tax_ids_after_fiscal_position.filtered_domain(company_domain)
                                    sign = -1 if line.qty >= 0 else 1
                                    check_refund = lambda x: x.qty * x.price_unit < 0
                                    is_refund = check_refund(line)
                                    tax_data = tax_ids.compute_all(price_unit=line.price_unit, quantity=abs(line.qty),
                                                                   currency=line.currency_id, is_refund=is_refund,
                                                                   fixed_multiplicator=sign, include_caba_tags=True)
                                    total_tax_percentage = sum(tax["amount"] for tax in tax_data.get("taxes", []))
                                    total_included = tax_data.get('total_included', 0)
                                    other_discount_exempt_tax += total_included * (total_tax_percentage / total_included)
                total_deductions = (
                        float(sd.get('senior_citizen_discount') or 0) +
                        float(sd.get('pwd_discount') or 0) +
                        float(sd.get('naac_discount') or 0) +
                        float(sd.get('spic_discount') or 0) +
                        float(sd.get('medal_discount') or 0) +
                        float(sd.get('other_discounts_two') or 0) +
                        float(sd.get('return_amount') or 0) +
                        float(sd.get('void_amount') or 0)
                )
                total_other = (
                    float(other_discount_exempt_tax or 0) +
                    float(sd.get('zero_rated_sales_tax') or 0) +
                    float(sd.get('vat_adjustment_tax') or 0)
                )
                total_vat_adjustment = (
                        float(sd.get('sc_discount_txn') or 0) +
                        float(sd.get('pwd_discount_txn') or 0) +
                        float(sd.get('spic_discount_txn') or 0) +
                        float(sd.get('medal_discount_txn') or 0) +
                        float(sd.get('vat_adjustment_tax') or 0) +
                        float(total_other or 0)
                )
                vat_payble = (
                        float(sd.get('vat_amount') or 0) - (
                        float(sd.get('spic_discount_txn') or 0) +
                        float(sd.get('medal_discount_txn') or 0)
                        # (float(sd.get('vat_adjustment_tax') or 0) * 2)
                )
                )
                net_sales = (
                        float(sd.get('gross_amount') or 0) - total_deductions - float(sd.get('vat_amount') or 0)
                )
                present_accumulated_sales = 0
                previous_accumulated_sales = 0
                if sd.get('z_counter') != 0:
                    present_accumulated_sales = sd.get('sales_for_day',0)
                else:
                    previous_accumulated_sales = sd.get('sales_for_day',0)


                sheet.write(row, 0, session.stop_at.strftime('%m-%d-%Y %H:%M:%S') if session.stop_at else '', num_fmt)
                sheet.write(row, 1, sd.get('start_invoice', 'N/A'), num_fmt)
                sheet.write(row, 2, sd.get('end_invoice', 'N/A'), num_fmt)
                sheet.write(row, 3, float(present_accumulated_sales), num_fmt)
                sheet.write(row, 4, float(previous_accumulated_sales), num_fmt)
                sheet.write(row, 5, '', num_fmt)
                sheet.write(row, 6, float(sd.get('gross_amount', 0)), num_fmt)
                sheet.write(row, 7, float(sd.get('vatable_sales', 0)), num_fmt)
                sheet.write(row, 8, float(sd.get('vat_amount', 0)), num_fmt)
                sheet.write(row, 9, float(sd.get('exempt_sales', 0)), num_fmt)
                sheet.write(row, 10, float(sd.get('zero_rated_sales', 0)), num_fmt)
                sheet.write(row, 11, float(sd.get('senior_citizen_discount', 0)), num_fmt)
                sheet.write(row, 12, float(sd.get('pwd_discount', 0)), num_fmt)
                sheet.write(row, 13, float(sd.get('naac_discount', 0)), num_fmt)
                sheet.write(row, 14, float(sd.get('spic_discount', 0)), num_fmt)
                sheet.write(row, 15, float(sd.get('medal_discount', 0)), num_fmt)
                sheet.write(row, 16, float(sd.get('other_discounts_two', 0)), num_fmt)
                sheet.write(row, 17, float(sd.get('return_amount', 0)), num_fmt)
                sheet.write(row, 18, float(sd.get('void_amount', 0)), num_fmt)
                sheet.write(row, 19, float(total_deductions), num_fmt)
                sheet.write(row, 20, float(sd.get('sc_discount_txn', 0)), num_fmt)
                sheet.write(row, 21, float(sd.get('pwd_discount_txn', 0)), num_fmt)
                sheet.write(row, 22, float(sd.get('spic_discount_txn', 0)), num_fmt)
                sheet.write(row, 23, float(sd.get('medal_discount_txn', 0)), num_fmt)
                sheet.write(row, 24, float(other_discount_exempt_tax), num_fmt)
                sheet.write(row, 25, float(sd.get('return_amount_tax', 0)), num_fmt)
                sheet.write(row, 26, float(total_other), num_fmt)
                sheet.write(row, 27, float(sd.get('vat_adjustment')), num_fmt)
                sheet.write(row, 28, float(vat_payble), num_fmt)
                sheet.write(row, 29, float(net_sales), num_fmt)
                sheet.write(row, 30, sd.get('', 0), num_fmt)
                sheet.write(row, 31, float(net_sales), num_fmt)
                sheet.write(row, 32, sd.get('reset_z_counter', 0), num_fmt)
                sheet.write(row, 33, sd.get('z_counter', 0), num_fmt)
                sheet.write(row, 34, '', num_fmt)

                row += 1

        workbook.close()
        output.seek(0)

        safe_shop_name = re.sub(r'[\\/*?:"<>|]', '', self.pos_id.name or 'POS').strip()
        tz = self.env.user.tz or 'UTC'
        user_tz = pytz.timezone(tz)
        local_date_from = pytz.UTC.localize(self.date_from).astimezone(user_tz)
        local_date_to = pytz.UTC.localize(self.date_to).astimezone(user_tz)
        date_to_str = local_date_to.strftime('%m-%d-%Y')
        date_from_str = local_date_from.strftime('%m-%d-%Y')

        attachment = self.env['ir.attachment'].sudo().create({
            'name': f'{safe_shop_name}.ANNEX_E1.{date_from_str} to {date_to_str}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })
        return attachment.id
    def _logic_e2(self):
        headers = [
            ('Date', '#A6A6A6'),
            ('Name of Senior Citizen(SC)', '#00B0F0'),
            ('OSCA ID No./SC ID No.', '#FFFF00'),
            ('SC TIN', '#B1A0C7'),
            ('SI Number', '#FFC000'),
            ('Sales (inclusive of VAT)', '#92D050'),
            ('VAT Amount', '#FF9900'),
            ('VAT Exempt Sales', '#D99694'),
            ('Discount', '#FFD966'),
            ('Net Sales', '#A6A6A6')
        ]
        value_prop = ["order.date_order.astimezone(user_timezone).strftime('%m-%d-%Y %H:%M:%S')",
                      "order.partner_id.name",
                      "order.partner_id.sc_id_no",
                      "order.partner_id.vat",
                      "order.invoice_number",
                      "f'{order.vat_sales:.2f}'",
                      "f'{order.amount_tax or 0:.2f}'",
                      "f'{order.vat_exempt_sales:.2f}'",
                      "f'{discount_5_calculate:.2f}'",
                      "f'{discount_20_calculate:.2f}'",
                      "f'{order.vat_exempt_sales - discount_20_calculate:.2f}'",
                      ]

        pos_id = self.pos_id.id
        date_from = self.date_from
        date_to = self.date_to

        # Get user timezone
        user_tz = 'UTC'

        # user_tz = self.env.user.tz or 'UTC'
        user_timezone = timezone(user_tz)
        utc_timezone = pytz.UTC
        if date_from:
            date_from_utc = user_timezone.localize(date_from.replace(tzinfo=None)).astimezone(utc_timezone)
        else:
            date_from_utc = fields.Datetime.now()
        if date_to:
            date_to_utc = user_timezone.localize(date_to.replace(tzinfo=None)).astimezone(utc_timezone)
        else:
            date_to_utc = fields.Datetime.now()

        # Build domain

        domain = [
            ('state', 'in', ['paid', 'done', 'invoiced']),
            ('date_order', '>=', date_from_utc),
            ('date_order', '<=', date_to_utc)
        ]

        if pos_id:
            domain.append(('config_id', '=', pos_id))

        # Search orders

        pos_orders = self.env['pos.order'].search(domain, order='date_order asc')
        order_no = []
        for order in pos_orders:
            if order.partner_id.senior_pwd_person == 'senior':
                order_no.append(order)

        return self._generate_excel_engine("E-2","ANNEX_E-2", "Senior Citizen Sales Book/Report", order_no, headers, value_prop)

    def _logic_e3(self):
        pos_id = self.pos_id.id
        date_from = self.date_from
        date_to = self.date_to

        # Get user timezone
        user_tz = 'UTC'

        # user_tz = self.env.user.tz or 'UTC'
        user_timezone = timezone(user_tz)
        utc_timezone = pytz.UTC
        if date_from:
            date_from_utc = user_timezone.localize(date_from.replace(tzinfo=None)).astimezone(utc_timezone)
        else:
            date_from_utc = fields.Datetime.now()
        if date_to:
            date_to_utc = user_timezone.localize(date_to.replace(tzinfo=None)).astimezone(utc_timezone)
        else:
            date_to_utc = fields.Datetime.now()

        # Build domain

        domain = [
            ('state', 'in', ['paid', 'done', 'invoiced']),
            ('date_order', '>=', date_from_utc),
            ('date_order', '<=', date_to_utc)
        ]

        if pos_id:
            domain.append(('config_id', '=', pos_id))

        # Search orders

        pos_orders = self.env['pos.order'].search(domain, order='date_order asc')
        order_no = []
        for order in pos_orders:
            if order.partner_id.senior_pwd_person == 'pwd':
                order_no.append(order)

        headers = [
            ("Date", "#A6A6A6"),
            ("Name of Person with Disability (PWD)", "#00B0F0"),
            ("PWD ID No.", "#FFFF00"),
            ("PWD TIN", "#B1A0C7"),
            ("SI Number", "#FFC000"),
            ("Sales (inclusive of VAT)", "#92D050"),
            ("VAT Amount", "#E26B0A"),
            ("VAT Exempt Sales", "#D9D9D9"),
            ("Discount", "#FFD966"),
            ("Net Sales", "#7F7F7F")]
        value_prop = ["order.date_order.astimezone(user_timezone).strftime('%m-%d-%Y %H:%M:%S')",
                      "order.partner_id.name",
                      "order.partner_id.pwd_id_no",
                      "order.partner_id.vat",
                      "order.invoice_number",
                      "f'{order.vat_sales:.2f}'",
                      "f'{order.amount_tax or 0:.2f}'",
                      "f'{order.vat_exempt_sales:.2f}'",
                      "f'{discount_5_calculate:.2f}'",
                      "f'{discount_20_calculate:.2f}'",
                      "f'{order.vat_exempt_sales - discount_20_calculate:.2f}'",
                      ]



        return self._generate_excel_engine("E-3","ANNEX_E3", "Persons with Disability Sales Book/Report", order_no, headers, value_prop)

    def _logic_e4(self):

        pos_id = self.pos_id.id
        date_from = self.date_from
        date_to = self.date_to

        # ---- Timezone convert
        user_tz = self.env.user.tz or 'UTC'
        user_timezone = timezone(user_tz)
        utc_timezone = pytz.UTC

        if date_from:
            date_from_utc = user_timezone.localize(
                date_from.replace(tzinfo=None)
            ).astimezone(utc_timezone)
        else:
            date_from_utc = fields.Datetime.now()

        if date_to:
            date_to_utc = user_timezone.localize(
                date_to.replace(tzinfo=None)
            ).astimezone(utc_timezone)
        else:
            date_to_utc = fields.Datetime.now()

        # ---- Domain
        domain = [
            ('state', 'in', ['paid', 'done', 'invoiced']),
            ('date_order', '>=', date_from_utc),
            ('date_order', '<=', date_to_utc)
        ]

        if pos_id:
            domain.append(('config_id', '=', pos_id))

        pos_orders = self.env['pos.order'].search(domain, order='date_order asc')

        # ---- Filter NAAC
        naac_orders = []
        for order in pos_orders:
            if order.partner_id and order.partner_id.senior_pwd_person == 'naac':
                naac_orders.append(order)

        # ---- Excel Create
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('E-4')

        title = self._make_format(workbook, size=14)
        header_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'font_size': 10
        })

        colors = {
            'gray': '#BFBFBF',
            'blue': '#00B0F0',
            'yellow': '#FFFF00',
            'orange': '#FFC000',
            'green': '#92D050',
            'light_yellow': '#FFD966',
        }
        fmt = {}
        for k, v in colors.items():
            f = self._make_format(workbook, v)
            f.set_bold(False)
            fmt[k] = f

        # ---- Column Width
        for col, w in zip('ABCDEFG', [18, 28, 18, 21, 22, 18, 18]):
            sheet.set_column(f'{col}:{col}', w)

        # ---- Dynamic Header
        raw_header = self.pos_id.receipt_header or ""
        header_lines = [self.pos_id.name] + [
            line.strip() for line in raw_header.split('\n') if line.strip()
        ]
        for i, text in enumerate(header_lines, start=1):
            sheet.merge_range(f'A{i}:E{i}', text, header_format)

        # ANNEX Box — always row 2-3
        sheet.merge_range('F2:G3', 'ANNEX "E-4"', title)

        # ---- Meta Data (dynamic row based on header size)
        next_row = len(header_lines) + 1

        software_info = f"{self.pos_id.name_software or ''}  {self.pos_id.version_software or ''}"
        release_info = f" {self.pos_id.no_release or ''}  {self.pos_id.release_date.strftime('%m/%d/%Y') if self.pos_id.release_date else ''}"

        tz = self.env.user.tz or 'UTC'
        user_tz = pytz.timezone(tz)
        local_date_from = pytz.UTC.localize(self.date_from).astimezone(user_tz)
        local_date_to = pytz.UTC.localize(self.date_to).astimezone(user_tz)
        date_from_str = local_date_from.strftime('%m/%d/%Y')
        date_to_str = local_date_to.strftime('%m/%d/%Y')

        meta = [
            (f'A{next_row}', f"Software Info: {software_info}  {release_info}"),
            (f'F{next_row}', f"Register ID: {self.pos_id.register_id_char or ''}"),
            (f'A{next_row + 1}', f"Serial No: {self.pos_id.x_serial_number or ''}"),
            (f'F{next_row + 1}', f"Date Range: {date_from_str} - {date_to_str}"),
            (f'A{next_row + 2}', f"Machine Identification Number: {self.pos_id.x_min_number or ''}"),
            (f'F{next_row + 2}', f"User ID: {self.env.user.name}"),
            (f'A{next_row + 3}', f"Branch: {self.pos_id.branch_name or self.pos_id.name}"),
            (f'F{next_row + 3}', f"Permit Number: {self.pos_id.permit_no or ''}"),
        ]
        for cell, text in meta:
            sheet.write(cell, text)

        # ---- Report Title
        title_row = next_row + 4
        sheet.merge_range(
            f'A{title_row}:G{title_row}',
            'National Athletes and Coaches Sales Book/Report',
            title
        )

        # ---- Table Header (dynamic rows)
        h1 = title_row + 1
        h3 = title_row + 3

        headers = [
            (f'A{h1}:A{h3}', 'Date', 'gray'),
            (f'B{h1}:B{h3}', 'Name of National\nAthlete/Coach', 'blue'),
            (f'C{h1}:C{h3}', 'PNSTM ID No.', 'yellow'),
            (f'D{h1}:D{h3}', 'SI\nNumber', 'orange'),
            (f'E{h1}:E{h3}', 'Gross\nSales/Receipts', 'green'),
            (f'F{h1}:F{h3}', 'Sales\nDiscount', 'light_yellow'),
            (f'G{h1}:G{h3}', 'Net Sales', 'gray'),
        ]

        left_format = workbook.add_format({
            'border': 1,
            'align': 'left'
        })
        right_number_format = workbook.add_format({
            'border': 1,
            'align': 'right',
            'num_format': '#,##0.00'
        })

        for rng, text, c in headers:
            sheet.merge_range(rng, text, fmt[c])

        # ---- Fill Data
        row = h3  # data starts after header
        for order in naac_orders:
            gross_sales = sum(line.price_subtotal for line in order.lines) + sum(
                line.discount_amount for line in order.lines) + sum(line.vat_amount for line in order)
            total_discount = sum(line.discount_amount for line in order.lines)
            net_sales = gross_sales - total_discount

            sheet.write(row, 0, order.date_order.astimezone(user_timezone).strftime('%m-%d-%Y %H:%M:%S'), left_format)
            sheet.write(row, 1, order.partner_id.name or '', left_format)
            sheet.write(row, 2, order.partner_id.naac_id_no or '', left_format)
            sheet.write(row, 3, order.invoice_number or '', left_format)
            sheet.write(row, 4, gross_sales, right_number_format)
            sheet.write(row, 5, total_discount, right_number_format)
            sheet.write(row, 6, net_sales, right_number_format)

            row += 1

        # ---- Finalize
        workbook.close()
        output.seek(0)

        safe_shop_name = re.sub(r'[\\/*?:"<>|]', '', self.pos_id.name or 'POS').strip()
        tz = self.env.user.tz or 'UTC'
        user_tz = pytz.timezone(tz)
        local_date_from = pytz.UTC.localize(self.date_from).astimezone(user_tz)
        local_date_to = pytz.UTC.localize(self.date_to).astimezone(user_tz)
        date_to_str = local_date_to.strftime('%m-%d-%Y')
        date_from_str = local_date_from.strftime('%m-%d-%Y')

        attachment = self.env['ir.attachment'].sudo().create({
            'name': f'{safe_shop_name}.ANNEX_E4.{date_from_str} to {date_to_str}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        return attachment.id
    def _logic_e5(self):
        pos_id = self.pos_id.id
        date_from = self.date_from
        date_to = self.date_to

        # ---- Timezone convert
        user_tz = self.env.user.tz or 'UTC'
        user_timezone = timezone(user_tz)
        utc_timezone = pytz.UTC

        if date_from:
            date_from_utc = user_timezone.localize(
                date_from.replace(tzinfo=None)
            ).astimezone(utc_timezone)
        else:
            date_from_utc = fields.Datetime.now()

        if date_to:
            date_to_utc = user_timezone.localize(
                date_to.replace(tzinfo=None)
            ).astimezone(utc_timezone)
        else:
            date_to_utc = fields.Datetime.now()

        # ---- Domain
        domain = [
            ('state', 'in', ['paid', 'done', 'invoiced']),
            ('date_order', '>=', date_from_utc),
            ('date_order', '<=', date_to_utc)
        ]

        if pos_id:
            domain.append(('config_id', '=', pos_id))

        pos_orders = self.env['pos.order'].search(domain, order='date_order asc')

        # ---- Filter spic only
        spic_orders = []
        for order in pos_orders:
            if order.partner_id.senior_pwd_person == 'spic':
                spic_orders.append(order)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('E-5')

        # ---- Formats
        title = self._make_format(workbook, size=14)
        header_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'font_size': 10
        })

        # Colors
        colors = {
            'gray': '#A6A6A6', 'dark_orange': '#ED7D31', 'gold': '#FFC000',
            'yellow': '#FFFF00', 'light_blue': '#B4C6E7', 'light_green': '#92D050',
            'cyan': '#00B0F0', 'purple': '#A5A5FF', 'magenta': '#FF33FF'
        }
        fmt = {}
        for k, v in colors.items():
            f = self._make_format(workbook, v)
            f.set_bold(False)
            f.set_text_wrap(True)
            fmt[k] = f

        # --- Column Width
        sheet.set_column('A:K', 14)
        sheet.set_column('A:A', 18)
        sheet.set_column('B:B', 28)
        sheet.set_column('D:D', 18)
        sheet.set_column('E:E', 16)
        sheet.set_column('F:F', 18)
        sheet.set_column('G:G', 19)
        sheet.set_column('I:J', 6)
        sheet.set_column('K:K', 11)

        # ---- Dynamic Header
        raw_header = self.pos_id.receipt_header or ""
        header_lines = [self.pos_id.name] + [
            line.strip() for line in raw_header.split('\n') if line.strip()
        ]
        for i, text in enumerate(header_lines, start=1):
            sheet.merge_range(f'A{i}:H{i}', text, header_format)

        # ANNEX Box — always row 2-3
        sheet.merge_range('I2:K3', 'ANNEX "E-5"', title)

        # ---- Meta Data (dynamic row based on header size)
        next_row = len(header_lines) + 1

        software_info = f"{self.pos_id.name_software or ''}  {self.pos_id.version_software or ''}"
        release_info = f" {self.pos_id.no_release or ''}  {self.pos_id.release_date.strftime('%m/%d/%Y') if self.pos_id.release_date else ''}"

        tz = self.env.user.tz or 'UTC'
        user_tz = pytz.timezone(tz)
        local_date_from = pytz.UTC.localize(self.date_from).astimezone(user_tz)
        local_date_to = pytz.UTC.localize(self.date_to).astimezone(user_tz)
        date_from_str = local_date_from.strftime('%m/%d/%Y')
        date_to_str = local_date_to.strftime('%m/%d/%Y')

        meta = [
            (f'A{next_row}', f"Software Info: {software_info}  {release_info}"),
            (f'F{next_row}', f"Register ID: {self.pos_id.register_id_char or ''}"),
            (f'A{next_row + 1}', f"Serial No: {self.pos_id.x_serial_number or ''}"),
            (f'F{next_row + 1}', f"Date Range: {date_from_str} - {date_to_str}"),
            (f'A{next_row + 2}', f"Machine Identification Number: {self.pos_id.x_min_number or ''}"),
            (f'F{next_row + 2}', f"User ID: {self.env.user.name}"),
            (f'A{next_row + 3}', f"Branch: {self.pos_id.branch_name or self.pos_id.name}"),
            (f'F{next_row + 3}', f"Permit Number: {self.pos_id.permit_no or ''}"),
        ]
        for cell, text in meta:
            sheet.write(cell, text)

        # ---- Report Title
        title_row = next_row + 4
        sheet.merge_range(f'A{title_row}:K{title_row}', 'Solo Parent Sales Book/Report', title)

        # ---- Table Header rows
        h1 = title_row + 1  # row 11 equivalent
        h4 = title_row + 4  # row 14 equivalent

        sheet.merge_range(f'A{h1}:A{h4}', 'Date', fmt['gray'])
        sheet.merge_range(f'B{h1}:B{h4}', 'Name of\nSolo Parent', fmt['dark_orange'])
        sheet.merge_range(f'C{h1}:C{h4}', 'SPIC No.', fmt['gold'])

        sheet.merge_range(f'D{h1}:D{h4 - 1}', 'Name of child', fmt['yellow'])
        sheet.write(h4 - 1, 3, '', fmt['light_blue'])
        sheet.merge_range(f'E{h1}:E{h4 - 1}', 'Birth Date of child', fmt['yellow'])
        sheet.write(h4 - 1, 4, '', fmt['light_blue'])
        sheet.merge_range(f'F{h1}:F{h4 - 1}', 'Age of child', fmt['yellow'])
        sheet.write(h4 - 1, 5, '', fmt['light_blue'])

        sheet.merge_range(f'G{h1}:G{h4}', 'SI\nNumber', fmt['light_green'])
        sheet.merge_range(f'H{h1}:H{h4}', 'Gross Sales', fmt['cyan'])
        sheet.merge_range(f'I{h1}:J{h4}', 'Discount', fmt['purple'])
        sheet.merge_range(f'K{h1}:K{h4}', 'Net Sales', fmt['magenta'])

        left_format = workbook.add_format({
            'border': 1,
            'align': 'left',
            'text_wrap': True
        })
        right_number_format = workbook.add_format({
            'border': 1,
            'align': 'right',
            'num_format': '#,##0.00'
        })

        # ---- Age Calculation
        today_local = datetime.datetime.now(user_timezone).date()

        def calc_age(birth_date, today):
            try:
                if not birth_date:
                    return ''
                years = today.year - birth_date.year
                months = today.month - birth_date.month
                if today.day < birth_date.day:
                    months -= 1
                if months < 0:
                    years -= 1
                    months += 12
                parts = []
                if years:
                    parts.append(f"{years} Year{'s' if years > 1 else ''}")
                if months:
                    parts.append(f"{months} Month{'s' if months > 1 else ''}")
                return ', '.join(parts) if parts else '0 Months'
            except Exception as e:
                _logger.error(f"CALC AGE ERROR: {e}")
                return ''

        # ---- Data Rows
        row = h4  # data starts after header
        for order in spic_orders:
            gross_sales = (order.total_sales or 0) + (order.vat_amount or 0)
            total_discount = sum(line.discount_amount for line in order.lines)
            net_sales = gross_sales - total_discount

            birth_date = order.partner_id.spic_child_birth_date
            age_str = calc_age(birth_date, today_local)

            sheet.write(row, 0, order.date_order.astimezone(user_timezone).strftime('%m-%d-%Y %H:%M:%S'), left_format)
            sheet.write(row, 1, order.partner_id.name or '', left_format)
            sheet.write(row, 2, order.partner_id.spic_id_no or '', left_format)
            sheet.write(row, 3, order.partner_id.spic_child_name or '', left_format)
            sheet.write(row, 4, birth_date.strftime('%m-%d-%Y') if birth_date else '', left_format)
            sheet.write(row, 5, age_str, left_format)
            sheet.write(row, 6, order.invoice_number or '', right_number_format)
            sheet.write(row, 7, gross_sales, right_number_format)
            sheet.merge_range(row, 8, row, 9, total_discount, right_number_format)
            sheet.write(row, 10, net_sales, right_number_format)

            row += 1

        workbook.close()
        output.seek(0)

        # ---- File Name (unchanged)
        safe_shop_name = re.sub(r'[\\/*?:"<>|]', '', self.pos_id.name or 'POS').strip()
        tz = self.env.user.tz or 'UTC'
        user_tz = pytz.timezone(tz)
        local_date_from = pytz.UTC.localize(self.date_from).astimezone(user_tz)
        local_date_to = pytz.UTC.localize(self.date_to).astimezone(user_tz)
        date_to_str = local_date_to.strftime('%m-%d-%Y')
        date_from_str = local_date_from.strftime('%m-%d-%Y')

        attachment = self.env['ir.attachment'].sudo().create({
            'name': f'{safe_shop_name}.ANNEX_E5.{date_from_str} to {date_to_str}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })
        return attachment.id
    # CONSOLIDATED EXCEL ENGINE

    def _make_format(self, workbook, bg=None, size=None):
        vals = {
            'border': 2,
            'align': 'center',
            'valign': 'vcenter',
            'bold': True,
            'text_wrap': True,
        }
        if bg:
            vals['bg_color'] = bg
        if size:
            vals['font_size'] = size
        return workbook.add_format(vals)

    def _generate_excel_engine(self, code,code2, title, order_no, headers, value_prop):
        fp = BytesIO()
        workbook = xlsxwriter.Workbook(fp)
        sheet = workbook.add_worksheet(f'Annex {code}')

        # --- Styles ---
        header_format = workbook.add_format({'bold': False, 'align': 'center', 'valign': 'vcenter', 'font_size': 13})
        title_format = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font_size': 17,'border': 2, })
        label_format = workbook.add_format({'font_size': 11, 'align': 'left'})
        data_format = workbook.add_format(
            {'font_size': 11, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'text_wrap': True})

        table_head = {
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'text_wrap': True
        }
        top_style = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'font_size': 10
        })
        # --- Header Section Fix ---
        raw_tin = self.pos_id.receipt_header or ''
        tin_no = raw_tin.split('#')[-1].strip() if '#' in raw_tin else ''
        raw_address = self.pos_id.receipt_header or ''
        address = ','.join(raw_address.split(',')[:5])

        header_lines = [self.pos_id.name] + [
            line.strip() for line in raw_address.split('\n') if line.strip()
        ]
        for i, text in enumerate(header_lines, start=1):
            sheet.merge_range(f'A{i}:H{i}', text, top_style)


        sheet.merge_range(0, 0, 0, 9, self.pos_id.name or '', top_style)
        sheet.merge_range(1, 8, 2, 10, f'ANNEX "{code}"', title_format)
        sheet.merge_range(6, 0, 6, 3,f"Software Info.: {self.pos_id.name_software or ''} {self.pos_id.version_software or ''} {self.pos_id.no_release or ''} {self.pos_id.release_date.strftime('%m-%d-%Y') or ''}",label_format)
        sheet.merge_range(7, 0, 7, 1, f"Serial No.: {self.pos_id.x_serial_number or ''}", label_format)
        sheet.merge_range(8, 0, 8, 2, f"Machine Identification No.: {self.pos_id.x_min_number or ''}", label_format)
        sheet.write(9, 0, f"Branch.: {self.pos_id.branch_name or ''}", label_format)
        sheet.write(6, 8, f"Register ID.: {self.pos_id.register_id_char or ''}", label_format)
        sheet.write(7, 8, f"Date Range.: {self.date_from.strftime('%m/%d/%Y')} - {self.date_to.strftime('%m/%d/%Y')}",
                    label_format)
        sheet.merge_range(8, 8, 8, 10, f"User ID.: {str(self.env.user.name) or ''}", label_format)
        sheet.write(9, 8, f"Permit Number.: {self.pos_id.permit_no or ''}", label_format)
        sheet.merge_range(10, 0, 10, 10, title, title_format)

        sheet.set_row(11, 30)
        sheet.set_row(12, 18)
        sheet.set_row(13, 18)
        sheet.set_column(6, 11, 20)

        col_idx = 0
        for text, color in headers:
            current_style = workbook.add_format({**table_head, 'bg_color': color})
            sheet.set_column(col_idx, col_idx, 15)

            if text == 'Discount':
                sheet.merge_range(11, col_idx, 11, col_idx + 1, text, current_style)
                sheet.merge_range(12, col_idx, 13, col_idx, "5%", current_style)
                sheet.set_column(col_idx, col_idx, 9)
                sheet.merge_range(12, col_idx + 1, 13, col_idx + 1, "20%", current_style)
                sheet.set_column(col_idx + 1, col_idx + 1, 9)
                col_idx += 2
                continue

            if col_idx == 5:
                sheet.set_column(col_idx, col_idx, 20)
                sheet.set_column(0, 0, 20)

            sheet.merge_range(11, col_idx, 13, col_idx, text, current_style)
            col_idx += 1
        if value_prop and order_no:
            row_idx = 14
            for order in order_no:
                col_idx = 0
                discount_calculate = 0
                discount_20_calculate = 0
                discount_5_calculate = 0
                for line in order.lines:
                    discount_calculate += line.discount_amount
                    if line.discount > 0:
                        if line.discount == 20:
                            discount_20_calculate += line.discount_amount
                        elif line.discount == 5:
                            discount_5_calculate += line.discount_amount

                user_tz_name = self.env.user.tz or 'UTC'
                user_timezone = timezone(user_tz_name)
                for prop in value_prop:
                    value = safe_eval(prop, {'order': order, 'discount_5_calculate': discount_5_calculate,
                                             'discount_20_calculate': discount_20_calculate,
                                             'discount_calculate': discount_calculate, 'user_timezone': user_timezone})
                    sheet.write(row_idx, col_idx, value or '', data_format)
                    col_idx += 1

                row_idx += 1

        workbook.close()
        fp.seek(0)

        safe_shop_name = re.sub(r'[\\/*?:"<>|]', '', self.pos_id.name or 'POS').strip()
        tz = self.env.user.tz or 'UTC'
        user_tz = pytz.timezone(tz)
        local_date_from = pytz.UTC.localize(self.date_from).astimezone(user_tz)
        local_date_to = pytz.UTC.localize(self.date_to).astimezone(user_tz)
        date_to_str = local_date_to.strftime('%m-%d-%Y')
        date_from_str = local_date_from.strftime('%m-%d-%Y')

        attachment = self.env['ir.attachment'].create({
            'name': f'{safe_shop_name}.{code2}.{date_from_str} to {date_to_str}.xlsx',
            'type': 'binary',
            'datas': encodebytes(fp.getvalue()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return attachment.id