"""Production statistics for managers, planners and supervisors.

Every figure and table is built from one authorized service call, so the backend
scope, filters and calculation rules apply identically to charts, drill-downs and
exports. Timing definitions live in `backend.service.statistics_service`.
"""
from datetime import date, timedelta

import plotly.graph_objects as go
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update

from frontend.auth import protect_callback
from frontend.login import top_bar
from frontend.common import (HANDLED_ERRORS, PERIODS, caller, clicked, failure, field, page_label,
                             period_range)
from frontend.i18n import translate
from frontend.supervisor import PAUSE_REASONS
from backend.service.statistics_service import (
    METRIC_LABELS, RECORD_COLUMNS, RECORDS_PAGE_SIZE, export_records_csv, get_records_service,
    get_statistics_service,
)

# The page is shared; the service still narrows each caller's visible records.
PAGE_ACCESS = ('manager', 'planner', 'supervisor')
# Rolling presets end today; "this month" is the default.
STAT_PERIODS = ('this_month', 'last_week', 'last_month', 'last_3_months', 'last_year', 'custom')

TABS = (('summary', 'Timing summary'), ('distribution', 'Duration distribution'),
        ('standard', 'Over standard'), ('bottlenecks', 'Bottlenecks'), ('trends', 'Trends'),
        ('throughput', 'Throughput & lead time'), ('risk', 'Current work at risk'),
        ('records', 'Records & export'))

FILTER_INPUTS = ('stat-product', 'stat-process', 'stat-step', 'stat-unit',
                 'stat-contractor', 'stat-order')
FILTER_KEYS = ('product_id', 'process_def_id', 'step_id', 'unit_id',
               'contractor_id', 'work_order_id')

PLOT_LAYOUT = dict(margin=dict(l=48, r=16, t=32, b=44), height=380,
                   paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                   font=dict(family='inherit', size=13),
                   legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0,
                               traceorder='normal'))
PLOT_CONFIG = {'displayModeBar': False, 'responsive': True}


def fill(template, **values):
    """Translate a sentence with placeholders, then put the numbers in.

    Output translation matches whole strings only, so a sentence built with an f-string
    would never find its catalogue entry.
    """
    return translate(template).format(**values)


def minutes(value, digits=1):
    """One consistent duration format: statistics are reported in minutes."""
    return '—' if value is None else f'{value:,.{digits}f} min'


def percent(value, digits=1):
    return '—' if value is None else f'{value:.{digits}f}%'


def tile(label, value, hint=None, drill=None):
    """A metric tile. Tiles with a drill key open their contributing records."""
    body = [html.Span(label, className='stat-tile-label'), html.Strong(value, className='stat-tile-value'),
            html.Small(hint or '', className='stat-tile-hint')]
    if drill is None:
        return html.Div(body, className='stat-tile')
    return html.Button(body, id={'type': 'stat-drill', 'key': drill}, n_clicks=0,
                       className='stat-tile stat-tile-clickable')


def empty(message):
    return html.Div(message, className='info-card planner-muted stat-empty')


def summary_table(block):
    """Raw against adjusted results, with the sample sizes behind each figure."""
    header = html.Tr([html.Th('Duration'), html.Th('Sample'), html.Th('Average'),
                      html.Th('Median'), html.Th('90th percentile'), html.Th('Excluded')])
    rows = []
    for metric in ('travel', 'process', 'combined'):
        entry = block[metric]
        for kind in ('raw', 'adjusted'):
            stats = entry[kind]
            rows.append(html.Tr([
                html.Td(f"{translate(entry['label'])} · {translate('Raw' if kind == 'raw' else 'Adjusted')}"),
                html.Td(f"{stats['count']:,}"), html.Td(minutes(stats['average'])),
                html.Td(minutes(stats['median'])), html.Td(minutes(stats['p90'])),
                html.Td('—' if kind == 'raw' else f"{entry['excluded']:,}"),
            ], className='stat-adjusted-row' if kind == 'adjusted' else None))
    return html.Table([html.Thead(header), html.Tbody(rows)], className='stat-table')


# Figures are data, not components, so output translation cannot reach their text; each
# label below is translated where the figure is built.
def distribution_figure(data):
    figure = go.Figure()
    if data['bins']:
        figure.add_bar(
            x=[(b['start'] + b['end']) / 2 for b in data['bins']],
            y=[b['count'] for b in data['bins']],
            width=[max(b['end'] - b['start'], 0.01) for b in data['bins']],
            name=translate('Executions'), marker_color='#3f6cb4',
            customdata=[[b['start'], b['end'], b['percent']] for b in data['bins']],
            hovertemplate=translate('%{customdata[0]:.1f}–%{customdata[1]:.1f} min<br>'
                                    '%{y} executions (%{customdata[2]:.1f}%)<extra></extra>'))
    if data['curve']:
        figure.add_scatter(x=[p['x'] for p in data['curve']], y=[p['y'] for p in data['curve']],
                           mode='lines', name=translate('Fitted normal curve'),
                           line=dict(color='#d1495b', width=2), hoverinfo='skip')
    for value, label, colour in ((data['mean'], 'Mean', '#2a9d8f'),
                                 (data['median'], 'Median', '#e9a23b'),
                                 (data['standard'], 'Standard', '#6b4fa0')):
        if value is not None:
            figure.add_vline(x=value, line=dict(color=colour, width=2, dash='dash'),
                             annotation_text=f'{translate(label)} {value:,.1f}',
                             annotation_position='top')
    figure.update_layout(**PLOT_LAYOUT, bargap=0.02,
                         xaxis_title=fill('{label} (minutes)', label=translate(data['label'])),
                         yaxis_title=translate('Executions'))
    return figure


def bottleneck_figure(rows):
    figure = go.Figure()
    labels = [f"{r['step_name']}<br>{r['group_label']}" for r in rows]
    for metric, colour in (('travel', '#e9a23b'), ('process', '#3f6cb4')):
        figure.add_bar(y=labels, x=[r[metric]['average'] or 0 for r in rows],
                       name=translate(METRIC_LABELS[metric]),
                       orientation='h', marker_color=colour,
                       customdata=[[r[metric]['count']] for r in rows],
                       hovertemplate=translate('%{x:.1f} min average<br>%{customdata[0]} '
                                               'observations<extra></extra>'))
    # Grow with the number of compared steps instead of using the shared fixed height.
    figure.update_layout(**{**PLOT_LAYOUT, 'height': max(320, 60 * len(rows) + 120)},
                         barmode='stack', xaxis_title=translate('Average minutes per piece'),
                         yaxis=dict(autorange='reversed'))
    return figure


def trend_figure(rows):
    figure = go.Figure()
    for metric, colour in (('travel', '#e9a23b'), ('process', '#3f6cb4'), ('combined', '#2a9d8f')):
        figure.add_scatter(x=[r['period'] for r in rows], y=[r[metric]['average'] for r in rows],
                           mode='lines+markers',
                           name=fill('{measure} average', measure=translate(METRIC_LABELS[metric])),
                           line=dict(color=colour),
                           customdata=[[r[metric]['count']] for r in rows],
                           hovertemplate=translate('%{y:.1f} min<br>%{customdata[0]} '
                                                   'observations<extra></extra>'))
    figure.add_scatter(x=[r['period'] for r in rows], y=[r['over_percent'] for r in rows],
                       mode='lines+markers', name=translate('Over standard (%)'), yaxis='y2',
                       line=dict(color='#d1495b', dash='dot'))
    figure.update_layout(**PLOT_LAYOUT, xaxis_title=translate('Period start'),
                         yaxis_title=translate('Minutes'),
                         yaxis2=dict(title=translate('Over standard (%)'), overlaying='y',
                                     side='right', rangemode='tozero'))
    return figure


def throughput_figure(rows):
    figure = go.Figure()
    figure.add_bar(x=[r['period'] for r in rows], y=[r['step_total'] for r in rows],
                   name=translate('Step completions'), marker_color='#3f6cb4')
    figure.add_bar(x=[r['period'] for r in rows], y=[r['finished_pieces'] for r in rows],
                   name=translate('Finished pieces'), marker_color='#2a9d8f')
    figure.add_scatter(x=[r['period'] for r in rows], y=[r['completed_orders'] for r in rows],
                       mode='lines+markers', name=translate('Completed work orders'), yaxis='y2',
                       line=dict(color='#d1495b'))
    figure.update_layout(**PLOT_LAYOUT, barmode='group', xaxis_title=translate('Period start'),
                         yaxis_title=translate('Pieces'),
                         yaxis2=dict(title=translate('Work orders'), overlaying='y',
                                     side='right', rangemode='tozero'))
    return figure


def record_table(records, caption=None):
    if not records:
        return empty('No records match this selection.')
    header = html.Tr([html.Th(label) for _, label in RECORD_COLUMNS])
    body = [html.Tr([html.Td(_cell(record[key])) for key, _ in RECORD_COLUMNS],
                    className='stat-outlier-row' if record['outlier'] else None)
            for record in records]
    return html.Div([
        html.P(caption, className='planner-muted') if caption else None,
        html.Div(html.Table([html.Thead(header), html.Tbody(body)], className='stat-table stat-records'),
                 className='stat-scroll'),
    ])


def _cell(value):
    if value is None:
        return '—'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, float):
        return f'{value:,.1f}'
    return str(value).replace('T', ' ')[:19] if 'T' in str(value) else str(value)


def statistics_page(actor=None):
    today = date.today()
    return html.Div(className='planner-page persistent-planner statistics-page', children=[
        top_bar('Production statistics', actor, 'statistics'),
        html.Div(className='planner-content', children=[
            html.Div([
                html.Div([html.H1('Production statistics'),
                          html.P(id='stat-scope', className='planner-muted')]),
                html.Span('Statistics', className='planner-badge'),
            ], className='planner-heading'),
            html.Div(id='stat-message', **{'aria-live': 'polite'}),
            html.Details([
                html.Summary('Filters'),
                html.Div(className='stat-filters', children=[
                    field('Period', dcc.Dropdown(id='stat-period', value='this_month', clearable=False,
                          options=[{'label': PERIODS[key], 'value': key} for key in STAT_PERIODS])),
                    field('Completed between', dcc.DatePickerRange(
                        id='stat-dates', start_date=today.replace(day=1).isoformat(),
                        end_date=today.isoformat(), display_format='D MMM YYYY')),
                    field('Product', dcc.Dropdown(id='stat-product', placeholder='All products')),
                    field('Process version', dcc.Dropdown(id='stat-process', placeholder='All processes')),
                    field('Step', dcc.Dropdown(id='stat-step', placeholder='All steps')),
                    field('Production unit', dcc.Dropdown(id='stat-unit', placeholder='All units')),
                    field('Contractor', dcc.Dropdown(id='stat-contractor', placeholder='All contractors')),
                    field('Work order', dcc.Dropdown(id='stat-order', placeholder='All work orders')),
                    field('Trend grain', dcc.Dropdown(id='stat-grain', value='week', clearable=False,
                        options=[{'label': 'Weekly', 'value': 'week'},
                                 {'label': 'Monthly', 'value': 'month'}])),
                ]),
                dcc.Checklist(id='stat-quick', value=[], className='stat-quick', inline=True,
                              options=[{'label': 'My units', 'value': 'my_units'},
                                       {'label': 'Orders I created', 'value': 'my_orders'}]),
                html.Div(className='stat-saved', children=[
                    dcc.Dropdown(id='stat-saved-pick', placeholder='Saved filter combinations'),
                    dcc.Input(id='stat-saved-name', placeholder='Name this combination',
                              className='form-input', maxLength=60),
                    html.Button('Save', id='stat-save', className='planner-secondary'),
                    html.Button('Delete', id='stat-delete', className='planner-text-button'),
                ]),
                html.P(id='stat-saved-message', className='planner-muted'),
            ], open=True, className='stat-filter-panel'),
            dcc.Tabs(id='stat-tab', value='summary',
                     children=[dcc.Tab(label=label, value=value) for value, label in TABS]),
            # Mounted once so the loading callback always has these inputs, and shown
            # only while the distribution tab is open.
            html.Div(id='stat-distribution-controls', className='stat-distribution-controls',
                     style={'display': 'none'}, children=[
                field('Process step', dcc.Dropdown(id='stat-distribution-step',
                                                   placeholder='Select a step', options=[])),
                field('Duration', dcc.Dropdown(
                    id='stat-distribution-metric', value='process', clearable=False,
                    options=[{'label': label, 'value': key} for key, label in METRIC_LABELS.items()])),
                field('Basis', dcc.Dropdown(
                    id='stat-distribution-basis', value='adjusted', clearable=False,
                    options=[{'label': 'Adjusted (outliers excluded)', 'value': 'adjusted'},
                             {'label': 'Raw (all executions)', 'value': 'raw'}])),
            ]),
            dcc.Loading(html.Div(id='stat-body', className='stat-body'), type='default'),
        ]),
        dcc.Store(id='stat-data'), dcc.Store(id='stat-drill'), dcc.Store(id='stat-records-position'),
        dcc.Store(id='stat-saved-store', storage_type='local'),
        dcc.Download(id='stat-download'),
    ])


def _options(rows, extra=None):
    return [{'label': row['name'] + (f" · {row[extra]}" if extra and row.get(extra) else ''),
             'value': row['id']} for row in rows]


def register_callbacks(app):

    def selection(dates, values, quick, grain, distribution=None):
        filters = {key: value for key, value in zip(FILTER_KEYS, values) if value is not None}
        if dates[0]:
            filters['date_from'] = dates[0]
        if dates[1]:
            filters['date_to'] = dates[1]
        for flag in quick or []:
            filters[flag] = True
        return dict(filters, grain=grain or 'week', **(distribution or {}))

    @app.callback(
        Output('stat-data', 'data'), Output('stat-message', 'children'), Output('stat-scope', 'children'),
        Input('stat-dates', 'start_date'), Input('stat-dates', 'end_date'),
        *[Input(name, 'value') for name in FILTER_INPUTS],
        Input('stat-quick', 'value'), Input('stat-grain', 'value'),
        Input('stat-distribution-step', 'value'), Input('stat-distribution-metric', 'value'),
        Input('stat-distribution-basis', 'value'))
    @protect_callback(*PAGE_ACCESS)
    def load(start, end, *rest):
        *values, quick, grain, step, metric, basis = rest
        try:
            data = get_statistics_service(*caller(app), **selection(
                (start, end), values, quick, grain,
                dict(distribution_step_id=step, distribution_metric=metric or 'process',
                     distribution_adjusted=basis != 'raw')))
            # Figures may be up to a minute old (see the statistics cache); say when they were read.
            as_of = translate('as of {time}').format(time=data['generated_at'].astimezone().strftime('%H:%M'))
            return data, '', f"{translate(data['scope_label'])} · {translate(data['period_label'])} · {as_of}"

        except HANDLED_ERRORS as exc:
            return None, failure(exc), ''

    @app.callback(
        *[Output(name, 'options') for name in FILTER_INPUTS],
        Output('stat-distribution-step', 'options'), Input('stat-data', 'data'))
    @protect_callback(*PAGE_ACCESS)
    def fill_options(data):
        if not data:
            return [[]] * (len(FILTER_INPUTS) + 1)
        options = data['options']
        return (_options(options['products']), _options(options['processes'], 'product_name'),
                _options(options['steps'], 'unit_name'), _options(options['units']),
                _options(options['contractors']), _options(options['orders']),
                [{'label': s['name'], 'value': s['id']} for s in data['distribution_steps']])

    @app.callback(Output('stat-distribution-step', 'value'), Input('stat-data', 'data'),
                  State('stat-distribution-step', 'value'))
    @protect_callback(*PAGE_ACCESS)
    def show_default_step(data, chosen):
        # The service falls back to the first step; show that choice in the control.
        if chosen is not None or not (data or {}).get('distribution'):
            return no_update
        return data['distribution']['step_id']

    @app.callback(Output('stat-body', 'children'), Input('stat-tab', 'value'),
                  Input('stat-data', 'data'), Input('stat-drill', 'data'))
    @protect_callback(*PAGE_ACCESS)
    def render(tab, data, drill):
        if data is None:
            return empty('Statistics are unavailable. Adjust the filters or retry.')
        return RENDERERS[tab](data, drill)

    # Each drill-down entry point owns its callback, because a chart or button that
    # belongs to another tab is not mounted while that tab is closed.
    @app.callback(Output('stat-drill', 'data'), Output('stat-tab', 'value'),
                  Input({'type': 'stat-drill', 'key': ALL}, 'n_clicks'),
                  prevent_initial_call=True)
    @protect_callback(*PAGE_ACCESS)
    def drill_from_tile(tiles):
        if not clicked():
            return no_update, no_update
        return {'key': ctx.triggered_id['key']}, 'records'

    @app.callback(Output('stat-drill', 'data', allow_duplicate=True),
                  Output('stat-tab', 'value', allow_duplicate=True),
                  Input('stat-bottleneck-chart', 'clickData'),
                  State('stat-data', 'data'), prevent_initial_call=True)
    @protect_callback(*PAGE_ACCESS)
    def drill_from_chart(click, data):
        if not click:
            return no_update, no_update
        row = (data or {}).get('bottlenecks', [])[click['points'][0]['pointIndex']]
        return {'step_id': row['step_id'],
                'label': f"{row['step_name']} · {row['group_label']}"}, 'records'

    @app.callback(Output('stat-drill', 'data', allow_duplicate=True),
                  Input('stat-clear-drill', 'n_clicks'), prevent_initial_call=True)
    @protect_callback(*PAGE_ACCESS)
    def clear_drilldown(clicks):
        return None if clicks else no_update

    @app.callback(Output('stat-distribution-controls', 'style'), Input('stat-tab', 'value'))
    @protect_callback(*PAGE_ACCESS)
    def show_distribution_controls(tab):
        return {} if tab == 'distribution' else {'display': 'none'}

    # A preset fills in the dates; picking dates by hand (or a saved combination) makes it custom.
    @app.callback(Output('stat-period', 'value'), Output('stat-dates', 'start_date'),
                  Output('stat-dates', 'end_date'), Input('stat-period', 'value'),
                  Input('stat-dates', 'start_date'), Input('stat-dates', 'end_date'),
                  prevent_initial_call=True)
    @protect_callback(*PAGE_ACCESS)
    def sync_period(period, start, end):
        if ctx.triggered_id == 'stat-period':
            if period == 'custom':
                return no_update, no_update, no_update
            first, last = period_range(period)
            return no_update, first.isoformat(), last.isoformat()
        chosen = next((key for key in STAT_PERIODS if key != 'custom' and
                       tuple(d.isoformat() for d in period_range(key)) == (start, end)), 'custom')
        return chosen, no_update, no_update

    @app.callback(Output('stat-records-position', 'data'),
                  Input('stat-records-prev', 'n_clicks'), Input('stat-records-next', 'n_clicks'),
                  State('stat-records-position', 'data'), State('stat-drill', 'data'),
                  State('stat-data', 'data'), prevent_initial_call=True)
    @protect_callback(*PAGE_ACCESS)
    def turn_records_page(previous, following, position, drill, data):
        number = records_page(position, drill, data)
        number += 1 if ctx.triggered_id == 'stat-records-next' else -1
        return {'number': max(1, number), 'drill': drill, 'filters': (data or {}).get('filters')}

    @app.callback(Output('stat-records-body', 'children'), Output('stat-records-prev', 'disabled'),
                  Output('stat-records-next', 'disabled'),
                  Input('stat-drill', 'data'), Input('stat-data', 'data'),
                  Input('stat-records-position', 'data'))
    @protect_callback(*PAGE_ACCESS)
    def records(drill, data, position):
        if not data:
            return empty('No data loaded.'), True, True
        number = records_page(position, drill, data)
        try:
            criteria = {'outliers': dict(only_outliers=True),
                        'over': dict(only_over_standard=True)}.get((drill or {}).get('key'), {})
            if (drill or {}).get('step_id'):
                criteria['step_id'] = drill['step_id']
            # One row more than a page says whether there is a next one; rows come from the cache.
            rows = get_records_service(*caller(app), offset=(number - 1) * RECORDS_PAGE_SIZE,
                                       limit=RECORDS_PAGE_SIZE + 1, **criteria, **data['filters'])
            more, rows = len(rows) > RECORDS_PAGE_SIZE, rows[:RECORDS_PAGE_SIZE]
            label = ((drill or {}).get('label') or {'outliers': 'Executions excluded as upper outliers',
                                                    'over': 'Executions over the standard process time'}
                     .get((drill or {}).get('key'), 'Contributing records'))
            return (record_table(rows, f"{translate(label)} · {page_label(number, len(rows), RECORDS_PAGE_SIZE)}"),
                    number <= 1, not more)
        except HANDLED_ERRORS as exc:
            return failure(exc), True, True

    @app.callback(Output('stat-download', 'data'), Input('stat-export', 'n_clicks'),
                  State('stat-data', 'data'), prevent_initial_call=True,
                  running=[(Output('stat-export', 'disabled'), True, False)])
    @protect_callback(*PAGE_ACCESS)
    def export(clicks, data):
        if not clicks or not data:
            return no_update
        csv_text = export_records_csv(*caller(app), **data['filters'])
        return dict(content=csv_text, filename=f"production-statistics-{date.today().isoformat()}.csv")

    @app.callback(Output('stat-saved-store', 'data'), Output('stat-saved-message', 'children'),
                  Input('stat-save', 'n_clicks'), Input('stat-delete', 'n_clicks'),
                  State('stat-saved-name', 'value'), State('stat-saved-pick', 'value'),
                  State('stat-data', 'data'), State('stat-saved-store', 'data'),
                  prevent_initial_call=True)
    @protect_callback(*PAGE_ACCESS)
    def save_combination(save, delete, name, picked, data, store):
        store = store or {}
        if ctx.triggered_id == 'stat-delete':
            if picked not in store:
                return no_update, 'Select a saved combination to delete.'
            return {k: v for k, v in store.items() if k != picked}, f'Deleted “{picked}”.'
        if not (name or '').strip():
            return no_update, 'Name the combination before saving it.'
        if not data:
            return no_update, 'Load statistics before saving these filters.'
        return {**store, name.strip(): data['filters']}, f'Saved “{name.strip()}”.'

    @app.callback(Output('stat-saved-pick', 'options'), Input('stat-saved-store', 'data'))
    @protect_callback(*PAGE_ACCESS)
    def list_saved(store):
        return [{'label': name, 'value': name} for name in sorted(store or {})]

    @app.callback(Output('stat-dates', 'start_date', allow_duplicate=True),
                  Output('stat-dates', 'end_date', allow_duplicate=True),
                  *[Output(name, 'value') for name in FILTER_INPUTS],
                  Output('stat-quick', 'value'),
                  Input('stat-saved-pick', 'value'), State('stat-saved-store', 'data'),
                  prevent_initial_call=True)
    @protect_callback(*PAGE_ACCESS)
    def apply_saved(picked, store):
        saved = (store or {}).get(picked)
        if not saved:
            return [no_update] * (len(FILTER_INPUTS) + 3)
        return (saved.get('date_from'), saved.get('date_to'),
                *[saved.get(key) for key in FILTER_KEYS],
                [flag for flag in ('my_units', 'my_orders') if saved.get(flag)])


def render_summary(data, _drill):
    timing = data['timing']
    quality = data['data_quality']
    return html.Div([
        html.Div([
            tile('Completed piece-step executions', f"{quality['executions']:,}",
                 'Timing observations in the selected period'),
            tile('Travel · median', minutes(timing['travel']['adjusted']['median']),
                 fill('{n} adjusted observations', n=f"{timing['travel']['adjusted']['count']:,}")),
            tile('Process · median', minutes(timing['process']['adjusted']['median']),
                 fill('{n} adjusted observations', n=f"{timing['process']['adjusted']['count']:,}")),
            tile('Combined · median', minutes(timing['combined']['adjusted']['median']),
                 fill('{n} adjusted observations', n=f"{timing['combined']['adjusted']['count']:,}")),
        ], className='stat-tiles'),
        html.Div([
            html.H2('Timing summaries'),
            html.P('Each figure counts one completed piece-step execution, because standard '
                   'times are defined per piece. Whole-order elapsed durations are reported '
                   'separately under Throughput & lead time.', className='planner-muted'),
            html.Div(summary_table(timing), className='stat-scroll'),
            html.P(fill(data['outlier_rule'], **data['outlier_values']),
                   className='planner-muted stat-rule'),
            html.Button('Inspect excluded outliers', id={'type': 'stat-drill', 'key': 'outliers'},
                        n_clicks=0, className='planner-text-button'),
        ], className='info-card'),
        html.Div([
            html.H2('Data quality'),
            html.Ul([
                html.Li(fill('{n} executions have no recorded previous-step timestamp, so their '
                             'travel time is unknown rather than zero.',
                             n=f"{quality['missing_travel_timestamp']:,}")),
                html.Li(fill('{n} executions have no configured standard time and are reported '
                             'as Not assessable.', n=f"{quality['missing_standard']:,}")),
                html.Li(fill('{n} pieces were marked Already prepared. They are finished '
                             'requirements with no processing, never zero-duration work.',
                             n=f"{quality['skipped_executions']:,}")),
                html.Li(fill('{n} executions across {orders} cancelled work orders are excluded '
                             'from every figure on this page.',
                             n=f"{quality['cancelled_executions']:,}",
                             orders=f"{quality['cancelled_orders']:,}")),
                html.Li([fill('{n} executions were paused for {minutes} in total. Paused time is '
                              'left out of active process time and over-standard figures, but '
                              'never out of lead times or due dates.',
                              n=f"{quality['paused_executions']:,}",
                              minutes=minutes(quality['paused_minutes'])),
                         html.Ul([html.Li(fill('{reason}: {minutes} across {n} pauses',
                                               reason=translate(PAUSE_REASONS[r['reason']]),
                                               minutes=minutes(r['minutes']), n=r['pauses']))
                                  for r in quality['pauses_by_reason']])
                         if quality['pauses_by_reason'] else None]),
            ]),
        ], className='info-card'),
    ])


def render_distribution(data, _drill):
    distribution = data['distribution']
    if not distribution or not distribution['count']:
        return empty(fill(distribution['note'], **distribution['note_values'])
                     if distribution and distribution['note']
                     else 'Select a process step with completed executions.')
    body = [
        html.Div([
            tile('Executions', f"{distribution['count']:,}"),
            tile('Mean', minutes(distribution['mean'])),
            tile('Median', minutes(distribution['median'])),
            tile('Standard deviation', minutes(distribution['stdev'])),
        ], className='stat-tiles'),
        dcc.Graph(figure=distribution_figure(distribution), config=PLOT_CONFIG,
                  id='stat-distribution-chart'),
        html.P(' '.join([translate('Bars are one standard deviation wide.')] + (
            [fill(distribution['note'], **distribution['note_values'])]
            if distribution['note'] else [])), className='planner-muted'),
    ]
    if distribution['metric'] != 'process':
        body.append(html.P('The standard process time is not drawn here: it applies to process '
                           'time only, never to travel or combined duration.', className='planner-muted'))
    elif distribution['standard'] is None:
        body.append(html.P('No single standard process time applies to this selection.',
                           className='planner-muted'))
    return html.Div(body, className='info-card')


def render_standard(data, _drill):
    over = data['over_standard']
    return html.Div([
        html.Div([
            tile('Executions over standard', f"{over['over_count']:,}",
                 'Completed piece-step executions', drill='over'),
            tile('Share of assessable executions', percent(over['over_percent']),
                 fill('{n} assessable of {total}', n=f"{over['assessable']:,}",
                      total=f"{over['executions']:,}")),
            tile('Affected work orders', f"{over['affected_orders']:,}", 'Distinct orders'),
            tile('Average excess', minutes(over['average_excess_minutes']),
                 fill('Average {percent} over standard',
                      percent=percent(over['average_percent_over']))),
            tile('Not assessable', f"{over['not_assessable']:,}", 'No configured standard time'),
        ], className='stat-tiles'),
        html.Div([
            html.H2('Severity bands'),
            html.Div(html.Table([html.Thead(html.Tr([html.Th('Band'), html.Th('Executions')])),
                                 html.Tbody([html.Tr([html.Td(name), html.Td(f'{count:,}')])
                                             for name, count in over['severity'].items()])],
                                className='stat-table'), className='stat-scroll'),
            html.P('Bands measure how far process time exceeded the standard: Minor up to 10%, '
                   'Moderate up to 25%, Major up to 50%, Severe above 50%.', className='planner-muted'),
            html.P('Process time is compared with the standard process time only. Travel and '
                   'combined duration are never judged against it.', className='planner-muted'),
            html.P('No historical standard is stored with each execution, so past work is compared '
                   'with the standard configured today. Treat these historical comparisons as '
                   'current-standard comparisons rather than the value in force at the time.',
                   className='planner-muted stat-rule'),
            html.P('Genuine long executions stay in these counts even when the adjusted timing '
                   'summaries exclude them as outliers.', className='planner-muted'),
        ], className='info-card'),
    ])


def render_bottlenecks(data, _drill):
    rows = data['bottlenecks']
    if not rows:
        return empty('No completed executions match these filters.')
    header = html.Tr([html.Th('Step'), html.Th('Product · process version'), html.Th('Unit'),
                      html.Th('Travel average'), html.Th('Process average'), html.Th('Over standard'),
                      html.Th('Ready to start')])
    return html.Div([
        html.Div([
            html.H2('Step comparison'),
            html.P('Steps are grouped by product and process version, so incomparable routes are '
                   'never averaged together. Select a bar to inspect its records, or use '
                   'the Records & export tab.',
                   className='planner-muted'),
            dcc.Graph(figure=bottleneck_figure(rows), config=PLOT_CONFIG, id='stat-bottleneck-chart'),
        ], className='info-card'),
        html.Div(html.Table([html.Thead(header), html.Tbody([
            html.Tr([html.Td(r['step_name']), html.Td(r['group_label']), html.Td(r['unit_name']),
                     html.Td(minutes(r['travel']['average'])), html.Td(minutes(r['process']['average'])),
                     html.Td(f"{r['over_count']:,} · {percent(r['over_percent'])}"),
                     html.Td(f"{r['ready_quantity']:,}")]) for r in rows])],
            className='stat-table'), className='info-card stat-scroll'),
        html.P('Ready-to-start quantity is live work waiting at each step, not a historical figure.',
               className='planner-muted'),
    ])


def render_trends(data, _drill):
    rows = data['trends']
    previous = data['previous_period']
    comparison = []
    if previous:
        current = {'travel': data['timing']['travel']['raw'], 'process': data['timing']['process']['raw'],
                   'combined': data['timing']['combined']['raw']}
        comparison = [html.Div([
            html.H2('Compared with the preceding equivalent period'),
            html.P(fill('Preceding period: {start} to {end} · {n} completed executions',
                        start=previous['date_from'], end=previous['date_to'],
                        n=f"{previous['executions']:,}"), className='planner-muted'),
            html.Div(html.Table([
                html.Thead(html.Tr([html.Th('Measure'), html.Th('Selected period'),
                                    html.Th('Preceding period'), html.Th('Change')])),
                html.Tbody([html.Tr([
                    html.Td(fill('{measure} average', measure=translate(METRIC_LABELS[metric]))),
                    html.Td(minutes(current[metric]['average'])),
                    html.Td(minutes(previous[metric]['average'])),
                    html.Td(_change(current[metric]['average'], previous[metric]['average'])),
                ]) for metric in ('travel', 'process', 'combined')] + [html.Tr([
                    html.Td('Over standard'), html.Td(percent(data['over_standard']['over_percent'])),
                    html.Td(percent(previous['over_percent'])),
                    html.Td(_change(data['over_standard']['over_percent'], previous['over_percent'], '%')),
                ])]),
            ], className='stat-table'), className='stat-scroll'),
        ], className='info-card')]
    if not rows:
        return html.Div([empty('No completed executions in the selected period.')] + comparison)
    return html.Div([
        html.Div([
            html.H2('Weekly timing and over-standard trend' if data['grain'] == 'week'
                    else 'Monthly timing and over-standard trend'),
            dcc.Graph(figure=trend_figure(rows), config=PLOT_CONFIG),
            html.Div(html.Table([
                html.Thead(html.Tr([html.Th('Period'), html.Th('Completions'), html.Th('Travel average'),
                                    html.Th('Process average'), html.Th('Combined average'),
                                    html.Th('Over standard')])),
                html.Tbody([html.Tr([
                    html.Td(r['period']), html.Td(f"{r['executions']:,}"),
                    html.Td(minutes(r['travel']['average'])), html.Td(minutes(r['process']['average'])),
                    html.Td(minutes(r['combined']['average'])), html.Td(percent(r['over_percent'])),
                ]) for r in rows]),
            ], className='stat-table'), className='stat-scroll'),
        ], className='info-card'),
    ] + comparison)


def _change(current, previous, suffix=' min'):
    if current is None or previous is None:
        return '—'
    delta = current - previous
    return f"{'+' if delta >= 0 else ''}{delta:,.1f}{suffix}"


def render_throughput(data, _drill):
    rows = data['throughput']
    lead = data['lead_times']
    tiles = html.Div([
        tile('Completed work orders', f"{lead['completed_orders']:,}", 'Completed in the period'),
        tile('Creation to completion', minutes(lead['creation_to_completion']['median']),
             fill('Median of {n} orders', n=f"{lead['creation_to_completion']['count']:,}")),
        tile('Production start to completion', minutes(lead['production_to_completion']['median']),
             fill('Median of {n} orders', n=f"{lead['production_to_completion']['count']:,}")),
        tile('Delivered by due date', percent(lead['on_time_percent']),
             fill('{n} of {total} dated orders', n=f"{lead['delivered_on_time']:,}",
                  total=f"{lead['due_dated_orders']:,}")),
    ], className='stat-tiles')
    notes = html.Div([
        html.P('Due-date delivery measures whole orders against their planned due date. It is a '
               'different measure from step-standard overruns, which compare per-piece process '
               'time with a step standard.', className='planner-muted'),
        html.P(fill('{n} completed orders have no recorded production start, so their '
                    'production lead time is unknown rather than zero.',
                    n=f"{lead['no_recorded_start']:,}"), className='planner-muted'),
        html.P('Step completions count each piece once per step it finishes; finished pieces count '
               'each piece once, when its last route step completes.', className='planner-muted'),
    ], className='info-card')
    if not rows:
        return html.Div([tiles, empty('No completions in the selected period.'), notes])
    return html.Div([tiles, html.Div([
        html.H2('Throughput'), dcc.Graph(figure=throughput_figure(rows), config=PLOT_CONFIG),
        html.Div(html.Table([
            html.Thead(html.Tr([html.Th('Period'), html.Th('Step completions'), html.Th('Finished pieces'),
                                html.Th('Completed work orders'), html.Th('Per step')])),
            html.Tbody([html.Tr([
                html.Td(r['period']), html.Td(f"{r['step_total']:,}"), html.Td(f"{r['finished_pieces']:,}"),
                html.Td(f"{r['completed_orders']:,}"),
                html.Td(', '.join(f"{s['step_name']}: {s['count']:,}" for s in r['steps']) or '—'),
            ]) for r in rows]),
        ], className='stat-table'), className='stat-scroll'),
    ], className='info-card'), notes])


def render_risk(data, _drill):
    risk = data['at_risk']
    def table(rows, columns, message):
        if not rows:
            return empty(message)
        return html.Div(html.Table([
            html.Thead(html.Tr([html.Th(label) for label, _ in columns])),
            html.Tbody([html.Tr([html.Td(_cell(get(row))) for _, get in columns]) for row in rows]),
        ], className='stat-table'), className='stat-scroll')
    return html.Div([
        html.Div([
            tile('Running beyond standard', f"{risk['running_count']:,}", 'Pieces in process now'),
            tile('Ready and waiting', f"{risk['waiting_count']:,}", 'Pieces with travel time running'),
            tile('Overdue work orders', f"{risk['overdue_count']:,}", 'Past their due date'),
        ], className='stat-tiles'),
        html.P('This section shows live work as of the moment the page loaded. It is not limited '
               'by the completed-between date filter, because none of these pieces has finished; '
               'the product, process, step, unit, contractor and work-order filters do apply.',
               className='planner-muted stat-rule'),
        html.Div([html.H2('Running pieces beyond standard process time'),
                  table(risk['running_over_standard'], (
                      ('Work order', lambda r: r['order_number']), ('Step', lambda r: r['step_name']),
                      ('Unit', lambda r: r['unit_name']), ('Product', lambda r: r['product_name']),
                      ('Elapsed', lambda r: minutes(r['elapsed_minutes'])),
                      ('Standard', lambda r: minutes(r['standard_minutes'])),
                      ('Over by', lambda r: minutes(r['excess_minutes']))),
                      'No running piece currently exceeds its standard process time.')],
                 className='info-card'),
        html.Div([html.H2('Ready pieces with the longest ongoing travel time'),
                  table(risk['waiting_longest'], (
                      ('Work order', lambda r: r['order_number']), ('Step', lambda r: r['step_name']),
                      ('Unit', lambda r: r['unit_name']), ('Product', lambda r: r['product_name']),
                      ('Waiting since', lambda r: r['predecessor_finished_at']),
                      ('Travel so far', lambda r: minutes(r['travel_minutes']))),
                      'No ready piece is waiting to start.'),
                  html.P('First route steps have no travel time and are not listed here.',
                         className='planner-muted')], className='info-card'),
        html.Div([html.H2('Work orders past their due date'),
                  table(risk['overdue_orders'], (
                      ('Work order', lambda r: r['order_number']), ('Product', lambda r: r['product_name']),
                      ('Contractor', lambda r: r['contractor_name']), ('Due', lambda r: r['due_date']),
                      ('Days late', lambda r: r['days_late']), ('Pieces', lambda r: r['pieces']),
                      ('Steps finished', lambda r: f"{r['finished_steps']}/{r['total_steps']}")),
                      'No outstanding work order is past its due date.')], className='info-card'),
    ])


def render_records(data, drill):
    return html.Div([
        html.Div([
            html.H2('Contributing records'),
            html.P('Every record keeps its order, product, process version, step, unit, timestamps, '
                   'durations, standard, excess and outlier status. Excluded outliers are shown, '
                   'never deleted.', className='planner-muted'),
            html.Div([
                html.Button('Export filtered records (CSV)', id='stat-export',
                            className='planner-secondary'),
                html.Button('Clear selection', id='stat-clear-drill', n_clicks=0,
                            className='planner-text-button',
                            style={'display': 'inline-block' if drill else 'none'}),
            ], className='stat-record-actions'),
            html.P('Exports apply the same access scope, filters and calculation rules as this page.',
                   className='planner-muted'),
        ], className='info-card'),
        dcc.Loading(html.Div(id='stat-records-body'), type='default'),
        html.Div([
            html.Button('‹ Previous', id='stat-records-prev', className='planner-text-button'),
            html.Button('Next ›', id='stat-records-next', className='planner-text-button'),
        ], className='overview-pages'),
    ])


def records_page(position, drill, data):
    """The records page to show: the stored one while the selection is unchanged, else 1."""
    if position and position.get('drill') == drill and position.get('filters') == (data or {}).get('filters'):
        return position['number']
    return 1


RENDERERS = {'summary': render_summary, 'distribution': render_distribution,
             'standard': render_standard, 'bottlenecks': render_bottlenecks,
             'trends': render_trends, 'throughput': render_throughput,
             'risk': render_risk, 'records': render_records}
