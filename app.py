from flask import Flask, render_template, request
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from dateutil.relativedelta import relativedelta  # Importando relativedelta

app = Flask(__name__)

# Função para calcular o número de dias úteis entre duas datas, incluindo feriados
def business_days_between(start_date, end_date, holidays):
    day = timedelta(days=1)
    business_days = 0
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() < 5 and current_date not in holidays:
            business_days += 1
        current_date += day
    return business_days

# Função para calcular o valor presente líquido (VPL)
def npv(rate, cash_flows):
    npv_value = 0
    for i, cash_flow in enumerate(cash_flows):
        npv_value += cash_flow / (1 + rate) ** i
    return npv_value

# Função para calcular a TIR
def calculate_irr(cash_flows):
    guess = 0.1  # Chute inicial de 10%
    tolerance = 1e-6
    max_iterations = 1000
    for _ in range(max_iterations):
        npv_value = npv(guess, cash_flows)
        if abs(npv_value) < tolerance:
            return guess
        # Derivada numérica da função de VPL
        deriv = (npv(guess + tolerance, cash_flows) - npv(guess, cash_flows)) / tolerance
        guess = guess - npv_value / deriv
    return guess

# Carregar o arquivo CSV de feriados e limpar os dados
def load_holidays(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    
    # Filtrar linhas que contêm datas válidas e têm o formato esperado
    filtered_lines = [line for line in lines if line[:2].isdigit() and line[2] == '/']
    
    # Criar um DataFrame com as linhas filtradas
    data = [line.strip().split(';')[:3] for line in filtered_lines]
    df = pd.DataFrame(data, columns=['Data', 'Dia da Semana', 'Feriado'])
    
    # Converter a coluna de datas para o tipo datetime
    df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y')
    
    return df

# Carregar e limpar o arquivo CSV
file_path_csv = 'feriados_nacionais.csv'
feriados_df_csv = load_holidays(file_path_csv)

# Converter a coluna de datas para o tipo datetime e criar um set de feriados
feriados = set(feriados_df_csv['Data'])

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
    end_date_base = datetime.strptime(request.form['end_date_base'], '%Y-%m-%d')
    rate_change_date = datetime.strptime(request.form['rate_change_date'], '%Y-%m-%d')
    annual_rate_pre_change = float(request.form['annual_rate_pre_change']) / 100
    annual_rate_post_change = float(request.form['annual_rate_post_change']) / 100
    purchase_price_range_start = int(request.form['purchase_price_range_start'])
    purchase_price_range_end = int(request.form['purchase_price_range_end'])
    purchase_price_range_step = int(request.form['purchase_price_range_step'])
    market_value = float(request.form['market_value'])

    purchase_price_range = range(purchase_price_range_start, purchase_price_range_end, purchase_price_range_step)
    
    daily_rate_pre_change = (1 + annual_rate_pre_change) ** (1 / 252) - 1
    daily_rate_post_change = (1 + annual_rate_post_change) ** (1 / 252) - 1
    
    delayed_dates = [end_date_base + relativedelta(months=i) for i in range(13)]
    
    results = []
    
    for purchase_price in purchase_price_range:
        for i, sale_date in enumerate(delayed_dates):
            if sale_date <= rate_change_date:
                days_between = business_days_between(start_date, sale_date, feriados)
                corrected_value = market_value * (1 + daily_rate_pre_change) ** days_between
            else:
                days_pre_change = business_days_between(start_date, rate_change_date, feriados)
                days_post_change = business_days_between(rate_change_date + timedelta(days=1), sale_date, feriados)
                corrected_value_pre_change = market_value * (1 + daily_rate_pre_change) ** days_pre_change
                corrected_value = corrected_value_pre_change * (1 + daily_rate_post_change) ** days_post_change
            
            cash_flows = [-purchase_price, corrected_value]
            irr = calculate_irr(cash_flows)
            annual_irr = (1 + irr) ** (252 / (days_between if sale_date <= rate_change_date else days_pre_change + days_post_change)) - 1
            results.append((purchase_price, sale_date, i, corrected_value, annual_irr * 100))
    
    df_results = pd.DataFrame(results, columns=['Purchase Price', 'Sale Date', 'Months of Delay', 'Corrected Value', 'Annual IRR'])
    
    x = df_results['Purchase Price'].unique()
    y = df_results['Months of Delay'].unique()
    z = df_results.pivot(index='Months of Delay', columns='Purchase Price', values='Annual IRR').values
    
    fig = go.Figure()
    
    fig.add_trace(go.Surface(
        x=x,
        y=y,
        z=z,
        colorscale='Viridis',
        colorbar=dict(title='Annual IRR (%)'),
        hovertemplate="TIR: %{z:.2f}%<br>Meses de atraso: %{y}<br>Preço de compra: R$%{x}<extra></extra>"
    ))
    
    fig.update_layout(
        scene=dict(
            xaxis_title='Purchase Price (R$)',
            yaxis_title='Months of Delay',
            zaxis_title='Annual IRR (%)',
            aspectratio=dict(x=1, y=1, z=0.7)
        ),
        title='Annual IRR over Time and Purchase Prices',
        autosize=True,
        width=700,
        height=700,
    )
    
    graph_html = pio.to_html(fig, full_html=False)
    
    return render_template('result.html', graph_html=graph_html)

if __name__ == '__main__':
    app.run(debug=True)
