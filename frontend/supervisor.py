"""Assigned process parts with persistent quantity actions and personal notifications."""
from datetime import datetime
from urllib.parse import parse_qs
from uuid import uuid4

from dash import html, dcc, Input, Output, State, ALL, ctx, no_update
from frontend.auth import protect_callback
from frontend.login import top_bar
from frontend.common import (HANDLED_ERRORS, caller, clicked, duration, failure, notice,
                             page_label, product_picture, scrap_badge)
from frontend.i18n import translate
from backend.service.supervisor_service import (
    get_supervisor_work, pause_step_service, read_notification_service, resume_step_service,
    update_part_service)
from backend.service.overview_service import get_order_summary_service
from frontend.manager import order_summary

# Cards shown at once. The queue is already limited to open and recently completed orders.
CARDS_PAGE_SIZE = 50
STATUSES = {'waiting': 'Waiting', 'ready': 'Ready', 'in_process': 'In process', 'partial': 'Partial', 'completed': 'Completed'}


def card_key(card):
    return ':'.join(str(card[k]) for k in ('work_order_id','process_def_id','process_step_id'))


def progress(card):
    percent = round(100 * card['completed'] / card['total'])
    return html.Div([
        html.Div([html.Span(f"{card['completed']} / {card['total']} pieces finished"), html.Strong(f'{percent}%')], className='part-progress-label'),
        html.Progress(value=card['completed'], max=card['total'],
                      **{'aria-label': 'Pieces finished at this step'}),
        html.P([f"{card['ready']} ready to start · {card['running']} running" + (f" · {card['skipped']} already prepared" if card['skipped'] else ''),
                scrap_badge(card['scrapped'])], className='planner-muted'),
    ])



def work_card(card, selected):
    return html.Button([
        html.Div([html.Strong(card['order_number']), html.Span(STATUSES[card['status']], className=f"part-status {card['status']}")], className='part-card-top'),
        html.Div([product_picture(card['product_type_id'], card['product_image_version']), html.Div([
            html.H3(card['product_name']), html.P(card['name']),
            html.Small(f"{card['unit_name']} · {card['process_name'] or 'Process'} v{card['version']}"),
        ])], className='part-product'), progress(card),
        html.Div([html.Span(f"Due {card['due_date']}" if card['due_date'] else 'No due date'),
                  html.Span('Overdue' if card['overdue'] else '')], className='part-card-footer'),
    ], id={'type':'part-select','key':card_key(card)}, n_clicks=0,
       className='part-card selected' if card_key(card)==selected else 'part-card',
       **{'aria-pressed':'true' if card_key(card)==selected else 'false'})


def quantity_input(count, key):
    # Remount prefilled numeric inputs: Dash 4.4 keeps stale stepper state on value updates.
    return html.Div(dcc.Input(id='part-quantity', type='number', value=count,
        min=1, max=count, step=1, autoFocus=key != 'initial', className='form-input'), key=key)


def shortcuts(count):
    """Quick quantities for the dialog. All means every eligible piece, not the order total."""
    amounts = [amount for amount in (1, 10) if amount < count]
    return [html.Button(str(amount), id={'type': 'part-quick', 'amount': amount}, n_clicks=0,
                        className='planner-text-button part-quick',
                        **{'aria-label': translate('Set quantity to {n}').format(n=amount)})
            for amount in amounts] + [
        html.Button(translate('All ({n})').format(n=count),
                    id={'type': 'part-quick', 'amount': count}, n_clicks=0,
                    className='planner-text-button part-quick')]


def outcome(action, quantity, card):
    """What happened, and what is left at this step, from counts read after the update."""
    done = {'start': 'started', 'complete': 'completed', 'skip': 'marked already prepared',
            'scrap': 'scrapped'}[action]
    first = translate('{q} pieces ' + done + '.').format(q=quantity)
    if card is None:
        return first
    if action == 'start':
        rest = translate('{running} running, {ready} ready to start.').format(**card)
    else:
        # Completed already includes skipped pieces; scrapped ones are resolved too.
        left = card['remaining']
        rest = (translate('{left} of {total} pieces still to finish at this step.').format(
                    left=left, total=card['total'])
                if left else translate('Every piece has finished this step.'))
    return f'{first} {rest}'


PAUSE_REASONS = {'break': 'Break', 'machine': 'Machine breakdown', 'material': 'Waiting for material',
                 'quality': 'Quality check', 'other': 'Other'}


def _local_time(value):
    # Card data passes through a browser store, so the time may arrive as ISO text.
    moment = datetime.fromisoformat(value) if isinstance(value, str) else value
    return moment.astimezone().strftime('%H:%M')


def pause_banner(pause):
    return html.Div([
        html.Strong(translate('Paused: {reason}').format(reason=translate(PAUSE_REASONS[pause['reason']]))),
        html.Span(translate(' since {time} by {name}').format(
            time=_local_time(pause['paused_at']), name=pause['paused_by_name'])),
        html.P('Paused time is recorded and shown in Statistics. Due dates do not move.',
               className='planner-muted'),
    ], className='planner-notice warning', role='status')


# The confirmation repeats the number, so a mistyped quantity is caught before it is saved.
CONFIRM_TEXT = {
    'start': 'You are about to start {q} pieces of {order} · {step}.',
    'complete': 'You are about to complete {q} pieces of {order} · {step}.',
    'skip': 'You are about to mark {q} pieces of {order} · {step} as already prepared.',
    'scrap': 'You are about to scrap {q} pieces of {order} · {step}. They will not continue '
             'to the next step.',
}
IRREVERSIBLE = 'This action is irreversible. Only a manager can correct a mistaken entry.'
TITLES = {'start': 'Start pieces', 'complete': 'Complete pieces',
          'skip': 'Already prepared — skip pieces', 'scrap': 'Scrap pieces'}
BUTTON_ACTIONS = {'part-start': 'start', 'part-complete': 'complete', 'part-skip': 'skip',
                  'part-scrap': 'scrap'}
# How many pieces each action may take, from the selected card.
ELIGIBLE = {'start': 'ready', 'complete': 'running', 'skip': 'unstarted', 'scrap': 'scrappable'}


def confirmation(form, quantity):
    return html.Div([
        html.Strong(translate(CONFIRM_TEXT[form['action']]).format(
            q=quantity, order=form['order_number'], step=form['step_name'])),
        html.P(IRREVERSIBLE),
    ], className='planner-notice warning', role='alert')


def supervisor_page(actor=None):
    return html.Div(className='planner-page persistent-planner supervisor-work-page', children=[
        top_bar('My work', actor, 'supervisor'),
        html.Div(className='planner-content',children=[
            html.Div([html.Div([html.H1('My process parts'),html.P('Process parts in your production units. Orders completed more than a month ago are in Order history.',className='planner-muted')]),
                html.Details([html.Summary(id='notification-bell',children='Notifications'),html.Div(id='supervisor-notifications')],className='notification-panel')],className='planner-heading'),
            html.Div(id='supervisor-load-message',**{'aria-live':'polite'}),html.Div(id='supervisor-action-message',**{'aria-live':'polite'}),
            html.Div([
                dcc.Input(id='supervisor-search',placeholder='Search order, part, description or product',debounce=True,className='form-input'),
                dcc.Dropdown(id='supervisor-unit',placeholder='All production units',options=[],clearable=True),
                dcc.Dropdown(id='supervisor-sort',value='due_asc',clearable=False,options=[
                    {'label':label,'value':value} for label,value in (
                        ('Due date · nearest first','due_asc'),('Due date · latest first','due_desc'),
                        ('Created · newest first','created_desc'),('Created · oldest first','created_asc'))]),
            ],className='supervisor-filters'),
            dcc.RadioItems(id='supervisor-status',value='all',options=[{'label':'All','value':'all'}]+[
                {'label':label,'value':value} for value,label in STATUSES.items()],className='supervisor-statuses',inline=True),
            html.Div([
                html.Div([html.Div(id='supervisor-cards',className='part-list'),
                          html.Div([html.Button('‹ Previous',id='supervisor-cards-prev',className='planner-text-button'),
                                    html.Span(id='supervisor-cards-label',className='planner-muted'),
                                    html.Button('Next ›',id='supervisor-cards-next',className='planner-text-button')],
                                   className='overview-pages')]),
                html.Div([
                    html.Div(id='supervisor-detail'),html.Div(id='supervisor-timer',className='part-timer'),
                    html.Div([html.Button('Start quantity',id='part-start',disabled=True,className='planner-secondary'),
                              html.Button('Complete quantity',id='part-complete',disabled=True,className='planner-secondary'),
                              html.Button('Already prepared',id='part-skip',disabled=True,className='planner-text-button'),
                              html.Button('Scrap pieces',id='part-scrap',disabled=True,className='planner-text-button danger')],className='part-actions'),
                    html.Div([dcc.Dropdown(id='pause-reason',value='break',clearable=False,searchable=False,
                                           options=[{'label':label,'value':key} for key,label in PAUSE_REASONS.items()]),
                              html.Button('Pause step',id='part-pause',disabled=True,className='planner-text-button'),
                              html.Button('Resume step',id='part-resume',disabled=True,className='planner-secondary')],
                             className='part-actions pause-controls'),
                    html.Div(id='supervisor-order-summary'),
                ],className='info-card part-detail'),
            ],className='supervisor-grid'),
        ]),
        dcc.Store(id='supervisor-data'),dcc.Store(id='selected-part'),dcc.Store(id='part-form'),
        dcc.Store(id='supervisor-cards-page',data=1),
        dcc.Store(id='supervisor-revision'),dcc.Store(id='notice-revision'),
        dcc.Interval(id='supervisor-refresh',interval=15000),dcc.Interval(id='supervisor-clock',interval=1000),
        html.Div(id='part-modal',style={'display':'none'},role='dialog',**{'aria-modal':'true','aria-labelledby':'part-form-title'},children=[
            html.Div([
                html.H2(id='part-form-title'),html.P(id='part-form-summary',className='planner-muted'),
                html.Label('Quantity (pieces)',htmlFor='part-quantity',className='form-label'),
                html.Div(quantity_input(1, 'initial'), id='part-quantity-input'),
                html.Div(shortcuts(1), id='part-shortcuts', className='part-shortcuts',
                         role='group', **{'aria-label': 'Quick quantities'}),
                html.Div([
                    html.Label('What should happen next?', htmlFor='part-corrective', className='form-label'),
                    dcc.RadioItems(id='part-corrective', value='replace', options=[
                        {'label': 'Make replacement pieces', 'value': 'replace'},
                        {'label': 'Review with a manager', 'value': 'review'},
                        {'label': 'No action needed', 'value': 'none'}], className='role-checklist'),
                    html.Label('What happened? (optional)', htmlFor='part-note', className='form-label'),
                    dcc.Textarea(id='part-note', className='form-input', maxLength=1000),
                ], id='part-scrap-fields', style={'display': 'none'}),
                html.Div(id='part-form-message',**{'aria-live':'polite'}),
                html.Div([html.Button('Cancel',id='part-cancel',className='planner-text-button'),
                          html.Button('Confirm & Update',id='part-confirm',className='planner-secondary')],className='part-actions'),
            ],className='part-modal-content'),
        ]),
    ])


def register_callbacks(app):

    @app.callback(Output('supervisor-data','data'),Output('supervisor-unit','options'),Output('supervisor-load-message','children'),
                  Input('supervisor-refresh','n_intervals'),Input('supervisor-search','value'),Input('supervisor-unit','value'),
                  Input('supervisor-sort','value'),Input('supervisor-status','value'),Input('supervisor-revision','data'),Input('notice-revision','data'))
    @protect_callback('supervisor')
    def load_work(tick,search,unit,sort,status,*_):
        try:
            result=get_supervisor_work(*caller(app),search=search or '',unit_id=unit,sort=sort,status=status)
            return result,[{'label':name,'value':key} for key,name in sorted(result['units'].items(),key=lambda pair:pair[1])],''
        except HANDLED_ERRORS as exc:
            return {},[],failure(exc)

    @app.callback(Output('selected-part','data'),Input({'type':'part-select','key':ALL},'n_clicks'),prevent_initial_call=True)
    @protect_callback('supervisor')
    def select_part(clicks):
        return ctx.triggered_id['key'] if clicked() else no_update

    @app.callback(Output('supervisor-cards-page','data'),
                  Input('supervisor-cards-prev','n_clicks'),Input('supervisor-cards-next','n_clicks'),
                  Input('supervisor-search','value'),Input('supervisor-unit','value'),
                  Input('supervisor-sort','value'),Input('supervisor-status','value'),
                  State('supervisor-cards-page','data'),prevent_initial_call=True)
    @protect_callback('supervisor')
    def change_cards_page(previous,following,search,unit,sort,status,number):
        # New filters start again at the first cards; the render clamps past the last page.
        if ctx.triggered_id=='supervisor-cards-next':
            return (number or 1)+1
        if ctx.triggered_id=='supervisor-cards-prev':
            return max(1,(number or 1)-1)
        return 1

    @app.callback(Output('supervisor-cards','children'),Output('supervisor-detail','children'),
                  Output('part-start','disabled'),Output('part-complete','disabled'),Output('part-skip','disabled'),Output('part-scrap','disabled'),
                  Output('part-pause','disabled'),Output('part-resume','disabled'),
                  Output('notification-bell','children'),Output('supervisor-notifications','children'),
                  Output('supervisor-cards-label','children'),Output('supervisor-cards-prev','disabled'),
                  Output('supervisor-cards-next','disabled'),
                  Input('supervisor-data','data'),Input('selected-part','data'),Input('supervisor-cards-page','data'))
    @protect_callback('supervisor')
    def render(data,selected,number):
        data=data or {};cards=data.get('cards',[]);notifications=data.get('notifications',[])
        card=next((c for c in cards if card_key(c)==selected),None)
        pages=max(1,-(-len(cards)//CARDS_PAGE_SIZE));number=min(max(1,number or 1),pages)
        shown=cards[(number-1)*CARDS_PAGE_SIZE:number*CARDS_PAGE_SIZE]
        listing=[work_card(c,selected) for c in shown] or html.Div('No parts in your supervised units match these filters.',className='info-card planner-muted')
        details=[html.H2('Select a process part'),html.P('Choose a card to see instructions and record quantities.',className='planner-muted')]
        if card:
            expected=duration(card['expected_seconds']) if card['expected_seconds'] else 'Unknown'
            details=[html.Span(card['order_number'],className='planner-badge'),html.H2(card['name']),
                html.P(f"{card['product_name']} · {card['unit_name']}"),progress(card),
                html.H3('Instructions'),html.P(card['instructions'] or 'No instructions provided.',className='step-instructions'),
                html.P(f"Standard: {duration(card['standard_time_seconds'])} per piece · {expected} for {card['total']} pieces",className='planner-muted')]
            if card['transfer_seconds'] is not None:
                details.append(html.P(f"Transfer time: {duration(card['transfer_seconds']) or '0s'} average per started piece", className='planner-muted'))
            if card.get('pause'):
                details.insert(2, pause_banner(card['pause']))
        notices=[html.Div([
            html.Strong(f"{n['order_number']} · {n['name']}"),
            html.P('New process part in your unit' if n['kind']=='assigned' else f"{n['event_count']} pieces have become ready"),
            html.Button('Mark read',id={'type':'notice-read','index':n['id']},n_clicks=0,className='planner-text-button') if n['read_at'] is None else html.Small('Read'),
        ],className='notification unread' if n['read_at'] is None else 'notification') for n in notifications]
        unread=sum(n['read_at'] is None for n in notifications)
        paused=bool(card and card.get('pause'))
        return (listing,details,not card or not card['ready'] or paused,not card or not card['running'] or paused,
                not card or not card['unstarted'],not card or not card['scrappable'],
                not card or not card['running'] or paused,not paused,
                f'Notifications ({unread})',notices or html.P('No notifications yet.'),
                page_label(number,len(shown),CARDS_PAGE_SIZE),number<=1,number>=pages)

    @app.callback(Output('notice-revision','data'),Input({'type':'notice-read','index':ALL},'n_clicks'),prevent_initial_call=True)
    @protect_callback('supervisor')
    def read_notice(clicks):
        if not clicked():
            return no_update
        read_notification_service(*caller(app),ctx.triggered_id['index'])
        return str(uuid4())

    @app.callback(Output('part-quantity-input','children',allow_duplicate=True),
                  Input({'type':'part-quick','amount':ALL},'n_clicks'),State('part-form','data'),
                  prevent_initial_call=True)
    @protect_callback('supervisor')
    def quick_quantity(clicks,form):
        if not form or not clicked():
            return no_update
        # The service still checks the amount; this only fills the field.
        return quantity_input(min(ctx.triggered_id['amount'],form['count']),str(uuid4()))

    @app.callback(Output('part-modal','style'),Output('part-form','data'),Output('part-quantity-input','children'),Output('part-form-title','children'),Output('part-form-summary','children'),
                  Output('part-form-message','children'),Output('supervisor-revision','data'),Output('supervisor-action-message','children'),
                  Output('part-shortcuts','children'),Output('part-scrap-fields','style'),Output('part-confirm','children'),
                  Input('part-start','n_clicks'),Input('part-complete','n_clicks'),Input('part-skip','n_clicks'),Input('part-scrap','n_clicks'),
                  Input('part-cancel','n_clicks'),Input('part-confirm','n_clicks'),
                  State('selected-part','data'),State('supervisor-data','data'),State('part-form','data'),State('part-quantity','value'),
                  State('part-corrective','value'),State('part-note','value'),
                  prevent_initial_call=True,running=[(Output('part-confirm','disabled'),True,False)])
    @protect_callback('supervisor')
    def quantity_action(start,complete,skip,scrap,cancel,confirm,selected,data,form,quantity,corrective,note):
        unchanged=[no_update]*11
        hidden={'display':'none'}
        if ctx.triggered_id=='part-cancel':
            return hidden,None,no_update,no_update,no_update,'',no_update,no_update,no_update,hidden,'Confirm & Update'
        if ctx.triggered_id in BUTTON_ACTIONS:
            card=next((c for c in (data or {}).get('cards',[]) if card_key(c)==selected),None)
            if not card:
                return unchanged
            action=BUTTON_ACTIONS[ctx.triggered_id]
            count=card[ELIGIBLE[action]]
            if not count:
                return unchanged
            form=dict(order_id=card['work_order_id'],process_id=card['process_def_id'],step_id=card['process_step_id'],
                      action=action,request_id=str(uuid4()),count=count,
                      order_number=card['order_number'],step_name=card['name'])
            summary=translate('{order} · {step} · {count} eligible of {total} pieces').format(order=card['order_number'],step=card['name'],count=count,total=card['total'])
            return ({},form,quantity_input(count, form['request_id']),TITLES[action],summary,'',no_update,'',
                    shortcuts(count),{} if action=='scrap' else hidden,'Confirm & Update')
        if ctx.triggered_id=='part-confirm' and form:
            if isinstance(quantity,float) and quantity.is_integer():
                quantity=int(quantity)
            if not isinstance(quantity,int) or not 1<=quantity<=form['count']:
                unchanged[5]=notice(translate('Enter a whole number from 1 to {n}.').format(n=form['count']),True)
                return unchanged
            if form.get('confirming')!=quantity:
                # First press: repeat the number and wait for a second, deliberate press.
                return (no_update,dict(form,confirming=quantity),no_update,no_update,no_update,
                        confirmation(form,quantity),no_update,no_update,no_update,no_update,
                        translate('Yes, record {q} pieces').format(q=quantity))
            try:
                actor,pool=caller(app)
                request={key:form[key] for key in ('order_id','process_id','step_id','action','request_id')}
                if form['action']=='scrap':
                    request.update(corrective=corrective or 'none',note=note)
                update_part_service(actor,pool,quantity=quantity,**request)
                # Re-read the step so the remaining quantity is the stored one.
                key=f"{form['order_id']}:{form['process_id']}:{form['step_id']}"
                card=next((c for c in get_supervisor_work(actor,pool)['cards'] if card_key(c)==key),None)
                message=outcome(form['action'],quantity,card)
                if form['action']=='scrap' and corrective in ('replace','review'):
                    message+=' '+translate('Replacement pieces were requested.' if corrective=='replace'
                                           else 'A review was requested.')
                return hidden,None,no_update,no_update,no_update,'',str(uuid4()),notice(message),no_update,hidden,'Confirm & Update'
            except HANDLED_ERRORS as exc:
                unchanged[5]=failure(exc)
        return unchanged

    @app.callback(Output('supervisor-search','value'),Input('url','search'))
    @protect_callback('supervisor')
    def search_from_link(search):
        # A scanned order sheet opens /supervisor?order=<number>: show that order's parts.
        values=parse_qs((search or '').lstrip('?')).get('order',[])
        return values[0] if values else no_update

    @app.callback(Output('supervisor-revision','data',allow_duplicate=True),
                  Output('supervisor-action-message','children',allow_duplicate=True),
                  Input('part-pause','n_clicks'),Input('part-resume','n_clicks'),
                  State('selected-part','data'),State('pause-reason','value'),prevent_initial_call=True)
    @protect_callback('supervisor')
    def pause_or_resume(pause,resume,selected,reason):
        if not selected or not clicked():
            return no_update,no_update
        order_id,process_id,step_id=(int(part) for part in selected.split(':'))
        try:
            if ctx.triggered_id=='part-pause':
                pause_step_service(*caller(app),order_id=order_id,process_id=process_id,step_id=step_id,reason=reason)
                return str(uuid4()),notice('Step paused. Resume it as soon as work continues.')
            resume_step_service(*caller(app),order_id=order_id,process_id=process_id,step_id=step_id)
            return str(uuid4()),notice('Step resumed.')
        except HANDLED_ERRORS as exc:
            return no_update,failure(exc)

    @app.callback(Output('supervisor-order-summary','children'),Input('selected-part','data'),Input('supervisor-revision','data'))
    @protect_callback('supervisor')
    def order_details(selected,_revision):
        # Summary only: supervisors never get the manager order page or its link.
        if not selected:
            return []
        try:
            return order_summary(get_order_summary_service(*caller(app),int(selected.split(':')[0])),link=False)
        except HANDLED_ERRORS as exc:
            return failure(exc)

    app.clientside_callback("""function(tick, data, selected) {
        const c = ((data || {}).cards || []).find(c => [c.work_order_id,c.process_def_id,c.process_step_id].join(':') === selected);
        if (!c || !c.started_at) return '';
        const end = c.finished_at ? Date.parse(c.finished_at) : Date.now();
        const seconds = Math.max(0, Math.floor((end-Date.parse(c.started_at))/1000));
        const h=Math.floor(seconds/3600), m=Math.floor(seconds%3600/60), s=seconds%60;
        return (c.finished_at ? 'Completed in ' : 'Elapsed ') + h+'h '+m+'m '+s+'s';
    }""",Output('supervisor-timer','children'),Input('supervisor-clock','n_intervals'),State('supervisor-data','data'),State('selected-part','data'))
