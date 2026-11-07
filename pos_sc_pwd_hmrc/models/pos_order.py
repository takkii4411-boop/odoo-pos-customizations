from odoo import models, fields, api, _
from markupsafe import Markup
import pytz
from datetime import datetime

import logging

_logger = logging.getLogger(__name__)


class PosOrderReprintLog(models.Model):
    _name = "pos.order.reprint.log"
    _description = "POS Order Reprint Log"

    pos_order_id = fields.Many2one('pos.order', string='POS Order', required=True, ondelete='cascade')
    reprint_by = fields.Char(string='Reprinted By', required=True)
    reason = fields.Text(string='Reason for Reprint')
    date = fields.Datetime(string='Reprint Date', default=fields.Datetime.now, required=True)


class PosOrder(models.Model):
    _inherit = "pos.order"

    invoice_number = fields.Char(
        string="Invoice Number",
        readonly=True,
        copy=False,
    )
    return_invoice_number = fields.Char(
        string="Adjustment Invoice Number",
        readonly=True,
        copy=False,
    )
    void_invoice_number = fields.Char(
        string="Adjustment Invoice Number",
        readonly=True,
        copy=False,
    )
    original_inv_ref = fields.Char(
        string="Original Invoice Ref.",
        readonly=True,
        copy=False,
    )


    transaction_number = fields.Char(
        string="Transaction Number",
        readonly=True,
        copy=False,
        help="Unique transaction number in format 00-00000000"
    )

    vat_sales = fields.Float(string="VAT Sales", default=0.0)
    vat_amount = fields.Float(string="VAT Amount", default=0.0)
    vat_exempt_sales = fields.Float(string="VAT Exempt Sales", default=0.0)
    zero_rated_sales = fields.Float(string="Zero Rated Sales", default=0.0)
    non_vat_sales = fields.Float(string="Non-VAT Sales", default=0.0)
    total_sales = fields.Float(string="Total Sales", default=0.0)
    total_vat = fields.Float(string="Total VAT", default=0.0)
    total_vat_exemption = fields.Float(string="Total VAT Exemption", default=0.0)
    hmrc_is_void_order = fields.Boolean(string="Is Void Order ?")
    hmrc_is_return_order = fields.Boolean(string="Is Return Order ?")
    hmrc_is_refund_order = fields.Boolean(string="Is Refund Order ?")
    return_message = fields.Text(string="Message", translate=True)
    ref_order_date = fields.Datetime(string='Date', readonly=True, index=True, default=fields.Datetime.now)
    deferred_payment_ids = fields.One2many('deferred.payment', 'pos_order_id', string='Deferred Payments')
    reprint_ids = fields.One2many('pos.order.reprint.log', 'pos_order_id', string='Reprint Logs')
    return_reason_message = fields.Char(string="Return/Refund Reason", translate=True)
    original_payment_method_id = fields.Many2one('pos.payment.method', string='Original Payment Method', readonly=True, copy=False)
    receipt_text = fields.Text(string="Receipt Text", readonly=True, copy=False)
    receipt_header_text = fields.Text(string="Receipt Text", readonly=True, copy=False)
    receipt_body_text = fields.Text(string="Receipt Text", readonly=True, copy=False)
    receipt_footer_text = fields.Text(string="Receipt Text", readonly=True, copy=False)

    def message_post(self, **kwargs):
        if kwargs.get('flag', False):
            message = Markup(kwargs.get('body', ''))
            kwargs['body'] = message
            del kwargs['flag']
            if kwargs.get('reprint', False):
                reprint_info = kwargs.get('reprint')
                _logger.info(f"\n\n\n Reprint Info: {reprint_info} \n\n\n")
                if reprint_info.get('date'):
                    date_str = reprint_info['date']
                    dt = datetime.strptime(date_str, "%m/%d/%Y %H:%M:%S")
                else:
                    dt = datetime.now(pytz.UTC)
                log_vals = {
                    'pos_order_id': self.id,
                    'reprint_by': reprint_info.get('reprint_by', 'Unknown'),
                    'reason': reprint_info.get('reason', ''),
                    'date': dt,
                }
                self.env['pos.order.reprint.log'].create(log_vals)
                del kwargs['reprint']

        return super().message_post(**kwargs)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Handle return/refund orders
            _logger.info(f"Creating POS Order with vals: {vals}")

        if vals.get('hmrc_is_return_order') and vals.get('original_inv_ref'):
            return_sequence = self._get_return_inv_sequence(vals)
            vals['invoice_number'] = self._generate_sequence_number(return_sequence)
            vals['return_invoice_number'] = vals['invoice_number'] + '-' + vals['original_inv_ref']
            vals['transaction_number'] = self._get_formatted_transaction_number(vals, 'order')

        elif vals.get('hmrc_is_refund_order') and vals.get('original_inv_ref'):
            return_sequence = self._get_return_inv_sequence(vals)
            vals['invoice_number'] = self._generate_sequence_number(return_sequence)
            vals['return_invoice_number'] = vals['invoice_number'] + '-' + vals['original_inv_ref']
            vals['transaction_number'] = self._get_formatted_transaction_number(vals, 'order')

        elif vals.get('hmrc_is_void_order') and vals.get('original_inv_ref'):
            void_sequence = self._get_void_inv_sequence(vals)
            vals['invoice_number'] = self._generate_sequence_number(void_sequence)
            vals['void_invoice_number'] = vals['invoice_number'] + '-' + vals['original_inv_ref']
            vals['transaction_number'] = self._get_formatted_transaction_number(vals, 'order')

        else:
            vals['invoice_number'] = self._get_formatted_number(vals, 'order')
            vals['transaction_number'] = self._get_formatted_transaction_number(vals, 'order')

        res = super().create(vals_list)

        for rec in res:
            if rec.return_message and rec.refunded_order_ids:
                message = rec.return_message

                if rec.return_invoice_number:
                    message += f'<span>Return/Refund Invoice No: {rec.return_invoice_number}</span><br/>'

                if rec.void_invoice_number:
                    message += f'<span>Void Invoice Number: {rec.void_invoice_number}</span><br/>'

                for original_order in rec.refunded_order_ids:
                    original_order.message_post(body=message, flag=True)

        return res

    def _compute_order_name(self):

        if len(self.refunded_order_ids) != 0:
            if self.hmrc_is_return_order and self.original_inv_ref:
                return ','.join(self.refunded_order_ids.mapped('name')) + _(' RETURN')
            elif self.hmrc_is_refund_order and self.original_inv_ref:
                return ','.join(self.refunded_order_ids.mapped('name')) + _(' REFUND')
            elif self.hmrc_is_void_order and self.original_inv_ref:
                return ','.join(self.refunded_order_ids.mapped('name')) + _(' VOID')
            else:
                return super()._compute_order_name()
        else:
            return self.session_id.config_id.sequence_id._next() + _(' SALE')

    def _get_invoice_sequence(self, vals):
        session_id = self._extract_session_id(vals)
        if session_id:
            sequence = self._get_sequence_from_session(session_id)
            if sequence:
                return sequence
        return self._get_fallback_sequence()

    def _get_return_inv_sequence(self, vals):
        session_id = self._extract_session_id(vals)
        if session_id:
            sequence = self._get_ret_sequence_from_session(session_id)
            if sequence:
                return sequence
        return self._get_fallback_sequence()

    def _get_void_inv_sequence(self, vals):
        session_id = self._extract_session_id(vals)
        if session_id:
            sequence = self._get_void_sequence_from_session(session_id)
            if sequence:
                return sequence
        return self._get_fallback_sequence()

    def _extract_session_id(self, vals):
        for field in ['session_id', 'pos_session_id', 'session']:
            value = vals.get(field)
            if value:
                return self._normalize_orm_command(value)
        return False

    def _normalize_orm_command(self, value):
        if isinstance(value, int):
            return value
        if isinstance(value, self.env['pos.session'].__class__):
            return value.id
        if not isinstance(value, (list, tuple)) or not value:
            return False

        try:
            if len(value) == 1 and isinstance(value[0], int):
                return value[0]
            elif len(value) >= 3 and isinstance(value[2], (list, tuple)) and value[2]:
                return value[2][0] if isinstance(value[2][0], int) else False
            elif len(value) >= 2 and isinstance(value[1], int):
                return value[1]
        except (IndexError, TypeError):
            pass
        return False

    def _get_sequence_from_session(self, session_id):
        try:
            session = self.env['pos.session'].browse(session_id)
            if session.exists() and session.config_id.order_sequence_id:
                return session.config_id.order_sequence_id
        except Exception:
            pass
        return None

    def _get_ret_sequence_from_session(self, session_id):
        try:
            session = self.env['pos.session'].browse(session_id)
            if session.exists() and session.config_id.return_order_sequence_id:
                return session.config_id.return_order_sequence_id
        except Exception:
            pass
        return None

    def _get_void_sequence_from_session(self, session_id):
        try:
            session = self.env['pos.session'].browse(session_id)
            if session.exists() and session.config_id.void_order_sequence_id:
                return session.config_id.void_order_sequence_id
        except Exception:
            pass
        return None

    def _get_fallback_sequence(self):
        return (self.env['ir.sequence'].search([('code', '=', 'pos.invoice.global')], limit=1) or
                self.env['ir.sequence'].search([('code', '=', 'pos.order')], limit=1) or
                self.env.ref('point_of_sale.sequence_pos_order', raise_if_not_found=False))

    def _generate_sequence_number(self, sequence):

        if not sequence:
            return self.env['ir.sequence'].next_by_code('pos.order') or '/'
        try:
            return sequence.next_by_id()
        except Exception:
            try:
                return self.env['ir.sequence'].next_by_code(sequence.code or 'pos.order')
            except Exception:
                return '/'

    def _get_formatted_number(self, vals, sequence_type='order'):

        session_id = self._extract_session_id(vals)

        if not session_id:
            fallback_seq = self._get_fallback_sequence()
            if fallback_seq:
                return fallback_seq.next_by_id()
            return '/'

        try:
            session = self.env['pos.session'].browse(session_id)
            if not session.exists():
                return '/'

            config = session.config_id
            formatted_number = config._get_formatted_sequence_number(sequence_type)

            _logger.info(f"Generated formatted invoice number: {formatted_number} for normal order")

            return formatted_number

        except Exception as e:
            _logger.error(f"Error generating formatted number: {str(e)}")
            fallback_seq = self._get_fallback_sequence()
            if fallback_seq:
                return fallback_seq.next_by_id()
            return '/'


    def _get_formatted_transaction_number(self, vals,sequence_type='order'):

        session_id = self._extract_session_id(vals)

        if not session_id:

            return f"00-{self.env['ir.sequence'].next_by_code('pos.transaction') or '00000001'}"

        try:
            session = self.env['pos.session'].browse(session_id)
            if not session.exists():
                return f"00-{self.env['ir.sequence'].next_by_code('pos.transaction') or '00000001'}"

            config = session.config_id


            formatted_txn_number = config._get_formatted_transaction_number()

            _logger.info(f"Generated formatted transaction number: {formatted_txn_number}")

            return formatted_txn_number

        except Exception as e:
            _logger.error(f"Error generating formatted transaction number: {str(e)}")
            return f"00-{self.env['ir.sequence'].next_by_code('pos.transaction') or '00000001'}"

    def _export_for_ui(self, order):
        timezone = pytz.timezone(self._context.get('tz') or self.env.user.tz or 'UTC')
        result = super(PosOrder, self)._export_for_ui(order)
        result.update({
            'invoice_number': order.invoice_number,
            'transaction_number': order.transaction_number,  # NEW
            'vat_sales': order.vat_sales,
            'vat_amount': order.vat_amount,
            'vat_exempt_sales': order.vat_exempt_sales,
            'zero_rated_sales': order.zero_rated_sales,
            'non_vat_sales': order.non_vat_sales,
            'total_sales': order.total_sales,
            'total_vat': order.total_vat,
            'total_vat_exemption': order.total_vat_exemption,
            'return_invoice_number': order.return_invoice_number,
            'void_invoice_number': order.void_invoice_number,
            'original_inv_ref': order.original_inv_ref,
            'hmrc_is_void_order': order.hmrc_is_void_order,
            'hmrc_is_return_order': order.hmrc_is_return_order,
            'hmrc_is_refund_order': order.hmrc_is_refund_order,
            'return_message': order.return_message,
            'return_reason_message': order.return_reason_message,
            'original_payment_method_id': order.original_payment_method_id.id if order.original_payment_method_id else False,
        })
        if order.ref_order_date:
            ref_date = (order.ref_order_date.astimezone(timezone))
            result['ref_order_date'] = str(ref_date)
        else:
            result['ref_order_date'] = False
        return result

    @api.model
    def _order_fields(self, ui_order):
        res = super(PosOrder, self)._order_fields(ui_order)
        res.update({
            "vat_sales": ui_order.get("vat_sales"),
            "vat_amount": ui_order.get("vat_amount"),
            "vat_exempt_sales": ui_order.get("vat_exempt_sales"),
            "zero_rated_sales": ui_order.get("zero_rated_sales"),
            "non_vat_sales": ui_order.get("non_vat_sales"),
            "total_sales": ui_order.get("total_sales"),
            "total_vat": ui_order.get("total_vat"),
            "total_vat_exemption": ui_order.get("total_vat_exemption"),
            "invoice_number": ui_order.get("invoice_number"),
            "transaction_number": ui_order.get("transaction_number"),  # NEW
            "return_invoice_number": ui_order.get("return_invoice_number"),
            "void_invoice_number": ui_order.get("void_invoice_number"),
            "original_inv_ref": ui_order.get("original_inv_ref"),
            "hmrc_is_void_order": ui_order.get("hmrc_is_void_order"),
            "hmrc_is_return_order": ui_order.get("hmrc_is_return_order"),
            "hmrc_is_refund_order": ui_order.get("hmrc_is_refund_order"),
            "return_message": ui_order.get("return_message"),
            "return_reason_message": ui_order.get("return_reason_message"),
            "receipt_text": ui_order.get("receipt_text"),
            "original_payment_method_id": ui_order.get("original_payment_method_id"),
            "ref_order_date": (
                ui_order["ref_order_date"].replace("T", " ")[:19]
                if ui_order.get("ref_order_date")
                else False
            ),
        })
        return res

    @api.model
    def _order_line_fields(self, line, session_id=None):
        res = super()._order_line_fields(line, session_id)

        ui_line = {}

        if isinstance(line, (list, tuple)) and len(line) >= 3:
            ui_line = line[2]
        elif isinstance(line, dict):
            ui_line = line

        if isinstance(ui_line, dict):
            applied_id = ui_line.get('applied_discount_id')

            if applied_id:
                if isinstance(applied_id, dict):
                    applied_id = applied_id.get('id')
                elif isinstance(applied_id, str) and applied_id.isdigit():
                    applied_id = int(applied_id)

            if not applied_id:
                discount_code = ui_line.get('applied_discount_code')
                discount_name = ui_line.get('applied_discount_name')
                on_line_text = ui_line.get('applied_on_line_text')

                if discount_code:
                    disc_rec = self.env['pos.special.discount'].sudo().search([
                        ('discount_code', '=', discount_code)
                    ], limit=1)
                    if disc_rec:
                        applied_id = disc_rec.id
                
                if not applied_id and on_line_text:
                    disc_rec = self.env['pos.special.discount'].sudo().search([
                        ('on_line_text', '=', on_line_text)
                    ], limit=1)
                    if disc_rec:
                        applied_id = disc_rec.id
                
                if not applied_id and discount_name:
                    disc_rec = self.env['pos.special.discount'].sudo().search([
                        ('name', '=', discount_name)
                    ], limit=1)
                    if disc_rec:
                        applied_id = disc_rec.id

            res[2]['applied_discount_id'] = applied_id or False
            res[2]['applied_discount_name'] = ui_line.get('applied_discount_name') or False
            res[2]['applied_on_line_text'] = ui_line.get('applied_on_line_text') or False
            res[2]['applied_discount_code'] = ui_line.get('applied_discount_code') or False

            # Fallback: if name or on_line_text is missing but we have an ID, fetch it from DB
            if (not res[2]['applied_discount_name'] or not res[2]['applied_on_line_text']) and res[2]['applied_discount_id']:
                disc_rec = self.env['pos.special.discount'].sudo().browse(res[2]['applied_discount_id'])
                if disc_rec.exists():
                    if not res[2]['applied_discount_name']:
                        res[2]['applied_discount_name'] = disc_rec.name
                    if not res[2]['applied_on_line_text']:
                        res[2]['applied_on_line_text'] = disc_rec.on_line_text or disc_rec.name

            res[2]['is_sc_line'] = ui_line.get('is_sc_line', False)
            res[2]['discount_amount'] = ui_line.get('discount_amount', 0)
            res[2]['vat_removed_amount'] = ui_line.get('vat_removed_amount', 0)
            res[2]['is_sc_bnpc_discount'] = ui_line.get('is_sc_bnpc_discount', False)
            res[2]['is_sc_bnpc_discount_amount'] = ui_line.get('is_sc_bnpc_discount_amount', 0)
            res[2]['net_vatable_sales'] = ui_line.get('net_vatable_sales', 0)
            res[2]['is_sc_line_discount'] = ui_line.get('is_sc_line_discount', False)
            res[2]['is_pwd_line_discount'] = ui_line.get('is_pwd_line_discount', False)
            res[2]['discount_vat_treatment'] = ui_line.get('discount_vat_treatment') or False
            res[2]['vat_reapplied'] = ui_line.get('vat_reapplied', 0)
            res[2]['vat_amount_output'] = ui_line.get('vat_amount_output', 0)
            res[2]['total_amount_due'] = ui_line.get('total_amount_due', 0)

        return res

    def _get_fields_for_order_line(self):
        fields = super()._get_fields_for_order_line()
        fields += [
            'applied_discount_id', 'applied_discount_name', 'applied_on_line_text',
            'is_sc_line', 'discount_amount', 'vat_removed_amount',
            'is_sc_bnpc_discount', 'is_sc_bnpc_discount_amount',
            'net_vatable_sales', 'is_sc_line_discount', 'is_pwd_line_discount',
            'discount_vat_treatment', 'vat_reapplied', 'vat_amount_output',
            'total_amount_due', 'applied_discount_code',
        ]
        return fields


    @api.model
    def get_current_invoice_number(self):
        sequence = self.env['ir.sequence'].search([('code', '=', 'pos.invoice.global')], limit=1)
        if not sequence:
            return False
        current_value = sequence.number_next_actual
        return str(current_value).zfill(sequence.padding or 8)


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    is_sc_line = fields.Boolean(string="Is SC Line", default=False)
    discount_amount = fields.Float(string="Discount Amount", default=0.0)
    vat_removed_amount = fields.Float(string="VAT Removed Amount", default=0.0)
    is_sc_bnpc_discount = fields.Boolean(string="Is SC BNPC Discount", default=False)
    is_sc_bnpc_discount_amount = fields.Float(string="SC BNPC Discount Amount", default=0.0)
    net_vatable_sales = fields.Float(string="Net Vatable Sales", default=0.0)
    applied_discount_id = fields.Many2one('pos.special.discount', string='Applied Special Discount')
    applied_discount_name = fields.Char(string='Applied Discount Name')
    applied_on_line_text = fields.Char(string='Applied On-Line Text')
    is_sc_line_discount = fields.Boolean(string='Is SC Line Discount', default=False)
    is_pwd_line_discount = fields.Boolean(string='Is PWD Line Discount', default=False)
    discount_vat_treatment = fields.Char(string='Discount VAT Treatment')
    applied_discount_code = fields.Char(string='Applied Discount Code')
    
    def _is_field_accepted(self, field):
        res = super()._is_field_accepted(field)
        if res:
            return True
        accepted_fields = [
            'applied_discount_id', 'applied_discount_name', 'applied_on_line_text',
            'is_sc_line', 'discount_amount', 'vat_removed_amount',
            'is_sc_bnpc_discount', 'is_sc_bnpc_discount_amount',
            'net_vatable_sales', 'is_sc_line_discount', 'is_pwd_line_discount',
            'discount_vat_treatment','applied_discount_code',
        ]
        return field in accepted_fields
    
    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)

    def write(self, vals):
        return super().write(vals)

    # def _export_for_ui(self, orderline):
    #     return {
    #         'is_sc_line': orderline.is_sc_line,
    #         'vat_removed_amount': orderline.vat_removed_amount,
    #         'discount_amount': orderline.discount_amount,
    #         'is_sc_bnpc_discount': orderline.is_sc_bnpc_discount,
    #         'is_sc_bnpc_discount_amount': orderline.is_sc_bnpc_discount_amount,
    #         'net_vatable_sales': orderline.net_vatable_sales,
    #         'is_sc_line_discount': orderline.is_sc_line_discount,
    #         'is_pwd_line_discount': orderline.is_pwd_line_discount,
    #         **super()._export_for_ui(orderline),
    #     }

    def _export_for_ui(self, orderline):
        result = super()._export_for_ui(orderline)
        result.update({
            'applied_discount_id': orderline.applied_discount_id.id if orderline.applied_discount_id else False,
            'applied_discount_name': orderline.applied_discount_name,
            'applied_on_line_text': orderline.applied_on_line_text,
            'applied_discount_code': orderline.applied_discount_code,
            'is_sc_line': orderline.is_sc_line,
            'vat_removed_amount': orderline.vat_removed_amount,
            'discount_amount': orderline.discount_amount,
            'is_sc_bnpc_discount': orderline.is_sc_bnpc_discount,
            'is_sc_bnpc_discount_amount': orderline.is_sc_bnpc_discount_amount,
            'net_vatable_sales': orderline.net_vatable_sales,
            'is_sc_line_discount': orderline.is_sc_line_discount,
            'is_pwd_line_discount': orderline.is_pwd_line_discount,
            'discount_vat_treatment': orderline.discount_vat_treatment,
        })
        return result