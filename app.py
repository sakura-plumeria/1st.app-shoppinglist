from flask import Flask, render_template, request, redirect
from datetime import datetime

app = Flask(__name__)
shopping_list = []

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'item' in request.form and 'category' in request.form:
            item = request.form.get('item')
            category = request.form.get('category') or '未分類'
            if item and category:
                shopping_list.append({
                    'item': item,
                    'category': category,
                    'purchased': False,
                    'added_at': datetime.now().strftime('%Y-%m-%d %H:%M')
                })

        elif 'delete' in request.form:
            index = int(request.form.get('delete'))
            if 0 <= index < len(shopping_list):
                shopping_list.pop(index)

        elif 'toggle' in request.form:
            index = int(request.form.get('toggle'))
            if 0 <= index < len(shopping_list):
                shopping_list[index]['purchased'] = not shopping_list[index]['purchased']

        return redirect('/')
    
    # カテゴリごとにまとめる
    categorized_items = {}
    for i, item in enumerate(shopping_list):
        cat = item['category']
        if cat not in categorized_items:
            categorized_items[cat] = []
        categorized_items[cat].append({'index': i, **item})

    return render_template('index.html', categorized_items=categorized_items)

if __name__ == '__main__':
    app.run(debug=True)