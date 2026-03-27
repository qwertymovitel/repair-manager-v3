import os
from flask import Flask, request, redirect, url_for, session, flash, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect, or_
from datetime import datetime

# --- INITIAL SETUP ---
base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, static_folder='static')
app.secret_key = "maputo-repair-v7-self-assign"

instance_path = os.path.join(base_dir, 'instance')
if not os.path.exists(instance_path): os.makedirs(instance_path)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, 'repairs.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELS ---
class Technician(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), default='1234')

class Repair(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(50), default='NEW') 
    is_ready = db.Column(db.Boolean, default=False)
    ready_date = db.Column(db.DateTime, nullable=True)
    delivery_date = db.Column(db.DateTime, nullable=True)
    is_warranty = db.Column(db.Boolean, default=False)
    client_complaint = db.Column(db.String(500), nullable=True)
    
    # Worksheet Fields
    client_name = db.Column(db.String(200)); client_phone = db.Column(db.String(50))
    client_address = db.Column(db.String(500)); serial_no = db.Column(db.String(100))
    problem_desc = db.Column(db.Text); tech_report = db.Column(db.Text)
    start_time = db.Column(db.String(50)); end_time = db.Column(db.String(50))
    materials = db.Column(db.Text); final_price = db.Column(db.String(50))
    
    technician_id = db.Column(db.Integer, db.ForeignKey('technician.id'), nullable=True)
    technician = db.relationship('Technician', backref='repairs')
    last_updated = db.Column(db.DateTime, default=datetime.now)
    quote_date = db.Column(db.DateTime, nullable=True)
    decision_date = db.Column(db.DateTime, nullable=True)

# --- JINJA FILTERS ---
@app.template_filter('format_dt')
def format_dt(value):
    if not value: return ""
    return value.strftime('%d/%m/%Y %H:%M')

@app.template_filter('time_ago')
def time_ago(dt):
    if not dt: return ""
    diff = datetime.now() - dt
    if diff.days > 0: return f"(Há {diff.days} dias)"
    if (diff.seconds // 60) < 60: return f"(Há {diff.seconds // 60} min)"
    return f"(Há {diff.seconds // 3600} horas)"

# --- SHARED NAVIGATION ---
NAV_HTML = """
<div class="p-5 bg-slate-900 text-white flex justify-between items-center shadow-lg">
    <div class="flex items-center gap-4">
        <img src="{{ url_for('static', filename='favicon.png') }}" class="w-10 h-10 invert">
        <div>
            <h1 class="text-2xl font-black italic tracking-tighter leading-none uppercase">Repair Manager v7</h1>
            <p class="text-[9px] text-slate-400 font-bold uppercase mt-1 tracking-widest">
                {% if session.get('role') %} 
                    Utilizador: {{ session.get('user_name') }} ({{ session.get('role')|upper }})
                {% else %} 
                    Acesso Público - Maputo
                {% endif %}
            </p>
        </div>
    </div>
    <div class="flex items-center gap-3">
        <a href="/" class="text-[10px] bg-slate-800 px-3 py-1.5 rounded font-bold uppercase border border-slate-700 hover:bg-slate-700 transition">Painel</a>
        <a href="/history" class="text-[10px] bg-slate-800 px-3 py-1.5 rounded font-bold uppercase border border-slate-700 hover:bg-slate-700 transition">Histórico</a>
        {% if session.get('role') %}
            <a href="/logout" class="bg-rose-600 px-4 py-1.5 rounded text-[10px] font-black uppercase hover:bg-rose-700">Sair</a>
        {% else %}
            <a href="/login" class="bg-blue-600 px-6 py-2 rounded text-xs font-black uppercase hover:bg-blue-700">Login</a>
        {% endif %}
    </div>
</div>
"""

# --- MAIN DASHBOARD TEMPLATE ---
MAIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8"><title>Repair Manager - Maputo</title>
    <link rel="icon" type="image/png" href="{{ url_for('static', filename='favicon.png') }}">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>table {width:100%; border-collapse:collapse;} th,td {border:1px solid #cbd5e1; padding:15px; vertical-align:top; width:33.33%;} .bg-warranty {background-color:#fff1f2;} .bg-active {background-color:#f0f9ff; border-left: 4px solid #0ea5e9;}</style>
</head>
<body class="bg-slate-200 p-4 font-sans text-slate-900">
    <div class="max-w-7xl mx-auto bg-white shadow-2xl rounded-xl overflow-hidden border">
        """ + NAV_HTML + """

        {% with messages = get_flashed_messages() %}
          {% if messages %}
            {% for message in messages %}
              <div class="bg-blue-600 text-white text-xs font-bold p-3 text-center uppercase tracking-widest">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <!-- SEARCH -->
        <div class="p-4 bg-slate-100 border-b flex justify-between items-center">
            <form action="/" method="GET" class="flex max-w-md gap-2">
                <input type="text" name="s" value="{{ s }}" placeholder="🔍 Pesquisar reparo ou técnico..." class="p-2 text-sm border-2 rounded-lg outline-none uppercase font-bold w-72 focus:border-blue-500">
                <button type="submit" class="bg-slate-800 text-white px-4 py-2 rounded-lg text-xs font-bold uppercase hover:bg-black">Filtrar</button>
                {% if s %}<a href="/" class="bg-slate-300 text-slate-700 px-4 py-2 rounded-lg text-xs font-bold flex items-center uppercase">Limpar</a>{% endif %}
            </form>
            <div class="text-[9px] text-slate-400 font-bold uppercase italic animate-pulse">Atualização Automática Ativa</div>
        </div>

        {% if session.get('role') == 'admin' %}
        <div class="p-4 border-b bg-slate-50 flex justify-between items-center">
            <form action="/add" method="POST" class="flex gap-2 flex-1">
                <input type="text" name="desc" placeholder="NOME DO EQUIPAMENTO E MODELO..." class="flex-1 border-2 p-2 rounded-lg text-sm font-bold uppercase outline-none focus:border-blue-500" required>
                <button type="submit" class="bg-blue-600 text-white px-8 py-2 rounded-lg font-black uppercase text-xs hover:bg-blue-700">Registar Entrada</button>
            </form>
            <button onclick="document.getElementById('m').classList.toggle('hidden')" class="ml-4 text-[9px] bg-slate-200 p-2 rounded font-black uppercase">Gerir Equipa</button>
        </div>
        <div id="m" class="hidden p-4 bg-slate-100 border-b">
             <div class="flex flex-wrap gap-2 mb-4">
                {% for t in techs %}<span class="bg-white border-2 px-3 py-1 rounded-full text-[10px] font-bold">{{t.name}} ({{t.password}}) <a href="/tech/delete/{{t.id}}" class="text-rose-500 font-black">×</a></span>{% endfor %}
            </div>
            <form action="/tech/manage" method="POST" class="flex gap-2">
                <input type="text" name="n" placeholder="Nome" class="border p-2 text-xs rounded w-40 uppercase font-bold"><input type="text" name="p" placeholder="Senha" class="border p-2 text-xs rounded w-40">
                <button type="submit" class="bg-emerald-600 text-white px-4 py-2 rounded text-[10px] font-bold uppercase shadow-sm">+ Add Técnico</button>
            </form>
        </div>
        {% endif %}

        <table class="w-full">
            <thead class="bg-slate-50 text-[11px] font-black text-slate-500 uppercase tracking-widest"><tr><th class="p-5 text-left text-blue-800">1. ENTRADA (NOVO)</th><th class="p-5 text-left text-amber-600">2. PENDENTE</th><th class="p-5 text-left text-emerald-700">3. FINALIZADO</th></tr></thead>
            <tbody>
                {% for r in repairs %}
                <tr class="{{ 'bg-warranty' if r.is_warranty else ('bg-active' if session.get('user_id') == r.technician_id else ('bg-white' if loop.index is even else 'bg-slate-50')) }} border-b border-slate-100">
                    <!-- COLUMN 1 -->
                    <td>
                        <div class="font-black text-slate-800 text-lg leading-tight uppercase">{{ r.description }}</div>
                        {% if r.is_warranty %}<div class="text-[9px] bg-rose-600 text-white px-2 py-0.5 rounded inline-block font-black mt-1 uppercase">Garantia</div>{% endif %}
                        <div class="text-[9px] text-slate-400 mt-2 mb-3 font-bold uppercase tracking-tight italic border-b pb-1">Entrada {{ r.last_updated | format_dt }}</div>
                        
                        <!-- THE "GO" BUTTON / STATUS LOGIC -->
                        <div class="flex items-center gap-2 mb-4">
                            {% if not r.technician_id %}
                                <!-- Unassigned: Click GO to claim -->
                                <a href="/assign_self/{{r.id}}" class="bg-blue-600 text-white px-6 py-1.5 rounded font-black text-xs uppercase shadow-md hover:bg-blue-700 transition">GO (Reivindicar)</a>
                            {% elif r.technician_id == session.get('user_id') %}
                                <!-- Assigned to ME -->
                                <div class="flex flex-col gap-1 w-full">
                                    <a href="/worksheet/{{r.id}}" class="bg-emerald-600 text-white px-4 py-1.5 rounded font-black text-xs uppercase text-center shadow-md hover:bg-emerald-700">GO (Folha de Obra)</a>
                                    <a href="/unassign/{{r.id}}" class="text-[9px] text-rose-500 font-bold uppercase underline text-center" onclick="return confirm('Remover atribuição?')">Largar este trabalho</a>
                                </div>
                            {% else %}
                                <!-- Assigned to SOMEONE ELSE -->
                                <div class="bg-slate-200 text-slate-500 px-4 py-1.5 rounded-full font-black text-[10px] uppercase border border-slate-300">
                                    🔧 {{ r.technician.name }} (Ocupado)
                                </div>
                            {% endif %}
                        </div>

                        {% if session.get('role') == 'admin' %}
                            <div class="mt-4 pt-4 border-t border-slate-200 flex gap-4">
                                {% if r.status == 'NEW' %}<a href="/update/{{r.id}}/quote" class="bg-amber-500 text-white text-[10px] px-3 py-1 rounded font-black uppercase">Enviar p/ Cotação</a>{% endif %}
                                <a href="/update/{{r.id}}/delete" class="text-[9px] text-slate-300 font-black uppercase hover:text-rose-600" onclick="return confirm('Eliminar?')">Eliminar</a>
                            </div>
                        {% endif %}
                    </td>

                    <!-- COLUMN 2 -->
                    <td>
                        {% if r.status != 'NEW' %}
                            <div class="text-[10px] font-black text-amber-600 uppercase italic">{% if r.status == 'PENDING' %}<span class="animate-pulse">●</span> Aguardando Decisão{% else %}Resposta Recebida{% endif %}</div>
                            <div class="text-[10px] text-slate-400 font-bold uppercase mt-1">{% if r.status == 'PENDING' %}Cotado {{ r.quote_date | time_ago }}{% else %}Decidido em {{ r.decision_date | format_dt }}{% endif %}</div>
                            {% if session.get('role') == 'admin' and r.status == 'PENDING' %}
                                <div class="flex flex-col gap-2 mt-4"><a href="/update/{{r.id}}/approve" class="bg-emerald-600 text-white text-center text-[11px] p-2 rounded font-black uppercase">Aprovar</a><a href="/update/{{r.id}}/return" class="bg-rose-600 text-white text-center text-[11px] p-2 rounded font-black uppercase">Devolver</a></div>
                            {% endif %}
                        {% endif %}
                    </td>

                    <!-- COLUMN 3 -->
                    <td>
                        {% if r.status == 'APPROVED' %}<div class="text-emerald-700 font-black text-2xl italic uppercase leading-none">✓ APROVADO</div>
                        {% elif r.status == 'RETURNED' %}<div class="text-rose-700 font-black text-2xl italic uppercase leading-none">✕ DEVOLUÇÃO</div>{% endif %}
                        
                        {% if r.decision_date %}<div class="text-[10px] text-slate-400 font-bold uppercase mt-1 border-b pb-1 mb-4">Confirmado {{ r.decision_date | format_dt }}</div>{% endif %}

                        <div class="mt-4">
                            {% if session.get('role') == 'tech' and r.technician_id == session.get('user_id') %}
                                <a href="/toggle_ready/{{r.id}}" class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border-2 transition-all {{ 'bg-emerald-100 border-emerald-500 text-emerald-800 font-black' if r.is_ready else 'bg-slate-50 border-slate-300 text-slate-400 font-bold' }}">
                                    <span class="text-[10px] uppercase">{{ '✓ EQUIPAMENTO PRONTO' if r.is_ready else '☐ MARCAR COMO PRONTO' }}</span>
                                </a>
                            {% else %}
                                <div class="text-[9px] font-black uppercase italic {{'text-emerald-600' if r.is_ready else 'text-slate-300'}}">{{ '✓ Equipamento Pronto' if r.is_ready else 'Em execução...' }}</div>
                            {% endif %}
                            {% if r.is_ready and r.ready_date %}<div class="text-[9px] text-emerald-600 font-bold uppercase mt-1">Pronto em: {{ r.ready_date | format_dt }}</div>{% endif %}
                        </div>

                        {% if session.get('role') == 'admin' and r.decision_date %}
                            <a href="/update/{{r.id}}/deliver" class="bg-slate-900 text-white block text-center text-[10px] p-3 rounded-lg font-black uppercase shadow-xl mt-6 hover:bg-black transition">Entregar ao Cliente</a>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <script>const isAdmin={{'true' if session.get('role') else 'false'}}, isS={{'true' if s else 'false'}}; if(!isAdmin && !isS){ let lastT = null; setInterval(async()=>{ try{ const r=await fetch('/api/last_update'); const d=await r.json(); if(lastT !== null && d.timestamp > lastT) location.reload(); lastT=d.timestamp; }catch(e){} }, 5000); }</script>
</body>
</html>
"""

# --- WORKSHEET (FOLHA DE OBRA) TEMPLATE ---
WORKSHEET_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt">
<head><meta charset="UTF-8"><title>Folha de Obra</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-slate-100 p-8 font-sans">
    <div class="max-w-4xl mx-auto bg-white p-10 shadow-2xl border-t-8 border-slate-900 rounded-b-xl">
        <div class="flex justify-between items-start border-b-2 border-slate-900 pb-4 mb-6 uppercase">
            <div><h1 class="text-3xl font-black italic tracking-tighter leading-none">IT Repair, Lda</h1><p class="text-[10px] text-slate-500 font-bold">Your Issue, Our Business</p></div>
            <div class="text-right"><h2 class="text-xl font-black">Obra #{{ r.id }}</h2><p class="text-xs font-bold mt-1">Técnico: <span class="bg-yellow-100 px-2">{{ r.technician.name }}</span></p></div>
        </div>

        <form action="/save_worksheet/{{ r.id }}" method="POST">
            <div class="grid grid-cols-2 gap-4 mb-6">
                <div><label class="text-[10px] font-black uppercase text-slate-400">Cliente</label><input type="text" name="client_name" value="{{ r.client_name or '' }}" class="w-full border-b p-1 text-sm font-bold uppercase focus:border-blue-500 outline-none"></div>
                <div><label class="text-[10px] font-black uppercase text-slate-400">Telemóvel</label><input type="text" name="client_phone" value="{{ r.client_phone or '' }}" class="w-full border-b p-1 text-sm font-bold focus:border-blue-500 outline-none"></div>
                <div class="col-span-2"><label class="text-[10px] font-black uppercase text-slate-400">Morada</label><input type="text" name="client_address" value="{{ r.client_address or '' }}" class="w-full border-b p-1 text-sm focus:border-blue-500 outline-none"></div>
            </div>

            <div class="bg-slate-50 p-4 rounded-lg border grid grid-cols-3 gap-4 mb-6">
                <div class="col-span-2"><label class="text-[10px] font-black uppercase text-slate-400">Equipamento</label><input type="text" name="desc" value="{{ r.description }}" class="w-full bg-transparent border-b p-1 font-black uppercase outline-none" required></div>
                <div><label class="text-[10px] font-black uppercase text-slate-400">Serial No</label><input type="text" name="serial" value="{{ r.serial_no or '' }}" class="w-full bg-transparent border-b p-1 uppercase outline-none"></div>
            </div>

            <div class="mb-4">
                <label class="text-[10px] font-black uppercase underline">Relatório Técnico / Trabalho Executado</label>
                <textarea name="tech_rep" class="w-full border p-2 h-32 text-sm rounded mt-1 font-bold uppercase focus:ring-2 ring-blue-100 outline-none" placeholder="...">{{ r.tech_report or '' }}</textarea>
            </div>

            <div class="grid grid-cols-3 gap-4 mb-6">
                <div><label class="text-[10px] font-black uppercase text-slate-400">Hora Início</label><input type="text" name="start" value="{{ r.start_time or '' }}" class="w-full border p-2 rounded text-xs"></div>
                <div><label class="text-[10px] font-black uppercase text-slate-400">Hora Fim</label><input type="text" name="end" value="{{ r.end_time or '' }}" class="w-full border p-2 rounded text-xs"></div>
                <div class="bg-blue-50 p-2 rounded">
                    <label class="text-[10px] font-black uppercase text-blue-600">Preço Final (Manager)</label>
                    <input type="text" name="price" value="{{ r.final_price or '' }}" class="w-full bg-transparent font-black text-lg text-blue-800" {{ 'disabled' if session.get('role') == 'tech' }}>
                </div>
            </div>

            <div class="flex justify-between items-center border-t-2 border-slate-900 pt-6">
                <a href="/" class="text-xs font-black text-slate-400 uppercase tracking-widest">← Voltar</a>
                <button type="submit" class="bg-slate-900 text-white px-10 py-3 rounded-xl font-black uppercase shadow-lg hover:bg-black transition">Guardar Folha de Obra</button>
            </div>
        </form>
    </div>
</body>
</html>
"""

# --- ROUTES & AUTH ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form['u']; p = request.form['p']
        if u == 'admin' and p == 'admin':
            session.update({'role': 'admin', 'user_id': 0, 'user_name': 'Admin'})
            return redirect(url_for('index'))
        tech = Technician.query.filter_by(name=u, password=p).first()
        if tech:
            session.update({'role': 'tech', 'user_id': tech.id, 'user_name': tech.name})
            return redirect(url_for('index'))
        flash('Login Inválido')
    return render_template_string('''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Login</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-slate-900 flex items-center justify-center h-screen font-sans"><div class="bg-white p-10 rounded-2xl shadow-2xl w-96 border-t-8 border-blue-600 text-center"><img src="/static/favicon.png" class="w-12 h-12 mx-auto mb-4"><h2 class="text-2xl font-black text-slate-800 mb-6 uppercase tracking-tighter italic">Entrar no Sistema</h2><form method="POST"><input type="text" name="u" placeholder="Nome do Técnico" class="w-full border-2 p-3 rounded mb-4 font-bold outline-none uppercase" required autofocus><input type="password" name="p" placeholder="Senha" class="w-full border-2 p-3 rounded mb-6 font-bold outline-none" required><button type="submit" class="w-full bg-blue-600 text-white p-4 rounded font-black uppercase">Entrar</button></form><a href="/" class="text-xs text-slate-400 block mt-4 underline uppercase">Painel Público</a></div></body></html>''')

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('index'))

@app.route('/')
def index():
    s = request.args.get('s', '').strip()
    query = Repair.query.filter(Repair.status != 'DELIVERED')
    if s: query = query.join(Technician, isouter=True).filter(or_(Repair.description.contains(s.upper()), Technician.name.contains(s)))
    repairs = query.order_by(Repair.last_updated.desc()).all()
    techs = Technician.query.order_by(Technician.name).all()
    return render_template_string(MAIN_TEMPLATE, repairs=repairs, techs=techs, s=s)

@app.route('/assign_self/<int:id>')
def assign_self(id):
    if not session.get('role'): return redirect(url_for('login'))
    r = Repair.query.get(id)
    if r.technician_id and r.technician_id != session.get('user_id'):
        flash('Este reparo já foi ocupado por outro técnico.')
    else:
        r.technician_id = session.get('user_id')
        r.last_updated = datetime.now()
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/unassign/<int:id>')
def unassign(id):
    if not session.get('role'): return redirect(url_for('index'))
    r = Repair.query.get(id)
    if r.technician_id == session.get('user_id'):
        r.technician_id = None
        r.last_updated = datetime.now()
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/worksheet/<int:id>')
def worksheet(id):
    if not session.get('role'): return redirect(url_for('login'))
    r = Repair.query.get(id)
    if session.get('role') == 'tech' and r.technician_id != session.get('user_id'):
        flash('Acesso negado: Este reparo não lhe pertence.')
        return redirect(url_for('index'))
    return render_template_string(WORKSHEET_TEMPLATE, r=r)

@app.route('/save_worksheet/<int:id>', methods=['POST'])
def save_worksheet(id):
    if not session.get('role'): return redirect(url_for('login'))
    r = Repair.query.get(id)
    r.client_name = request.form.get('client_name'); r.client_phone = request.form.get('client_phone')
    r.client_address = request.form.get('client_address'); r.description = request.form.get('desc').upper()
    r.serial_no = request.form.get('serial'); r.tech_report = request.form.get('tech_rep')
    r.start_time = request.form.get('start'); r.end_time = request.form.get('end')
    if session.get('role') == 'admin': r.final_price = request.form.get('price')
    r.last_updated = datetime.now(); db.session.commit()
    return redirect(url_for('index'))

@app.route('/toggle_ready/<int:id>')
def toggle_ready(id):
    if session.get('role') != 'tech': return redirect(url_for('index'))
    r = Repair.query.get(id); r.is_ready = not r.is_ready; r.ready_date = datetime.now() if r.is_ready else None; r.last_updated = datetime.now(); db.session.commit()
    return redirect(url_for('index'))

@app.route('/update/<int:id>/<action>')
def update(id, action):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    r = Repair.query.get(id); r.last_updated = datetime.now()
    if action == 'quote': r.status = 'PENDING'; r.quote_date = datetime.now()
    elif action == 'approve': r.status = 'APPROVED'; r.decision_date = datetime.now()
    elif action == 'return': r.status = 'RETURNED'; r.decision_date = datetime.now()
    elif action == 'deliver': r.status = 'DELIVERED'; r.delivery_date = datetime.now()
    elif action == 'delete': db.session.delete(r)
    db.session.commit(); return redirect(url_for('index'))

@app.route('/tech/manage', methods=['POST'])
def add_tech():
    if session.get('role') != 'admin': return redirect(url_for('index'))
    n = request.form.get('n'); p = request.form.get('p')
    if n: db.session.add(Technician(name=n.strip(), password=p)); db.session.commit()
    return redirect(url_for('index'))

@app.route('/tech/delete/<int:id>')
def delete_tech(id):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    db.session.delete(Technician.query.get(id)); db.session.commit(); return redirect(url_for('index'))

@app.route('/api/last_update')
def last_update():
    latest = Repair.query.order_by(Repair.last_updated.desc()).first()
    return jsonify({"timestamp": latest.last_updated.timestamp() if latest else 0})

# --- AUTO-FIX & SEED ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        try:
            ins = inspect(db.engine); cols = [c['name'] for c in ins.get_columns('repair')]
            with db.engine.connect() as conn:
                for c in ['client_name','client_phone','client_address','serial_no','problem_desc','tech_report','start_time','end_time','materials','final_price','delivery_date']:
                    if c not in cols: conn.execute(text(f'ALTER TABLE repair ADD COLUMN {c} TEXT'))
                if 'is_warranty' not in cols: conn.execute(text('ALTER TABLE repair ADD COLUMN is_warranty BOOLEAN DEFAULT 0'))
                conn.commit()
        except: pass
        if Technician.query.count() == 0:
            for n in ["Homo", "Willard", "Madeline", "Reginaldo", "Dinis"]: db.session.add(Technician(name=n))
            db.session.commit()
    app.run(host='0.0.0.0', port=5000)
