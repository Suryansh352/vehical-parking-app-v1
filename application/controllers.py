from flask import Flask, flash, render_template,redirect,request, session,url_for
from flask import current_app as app
from datetime import datetime
import matplotlib.pyplot as plt
import io
import base64
from collections import defaultdict
import calendar


from .models import *

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form.get('password')
        this_user = User.query.filter_by(email=email).first()
        if this_user:
            if this_user.password_hash == password:
                session['user_email'] = this_user.email 
                if this_user.is_admin:
                    return redirect(url_for('admin_dashboard')) 
                else:
                    return redirect('/user-dashboard')  
            else:
                return "Invalid password!"
        else:
            return "User not found!"
        return "Login successful!"
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        full_name = request.form['name']
        address=request.form['address']
        pin_code = request.form['pincode']
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            return "Email already used"
        else:
            user=User(email=email,password_hash=password)
            db.session.add(user)
            db.session.commit()
        return "Registration successful!"
    return render_template('register.html')

@app.route('/create', methods=['GET', 'POST'])
def create_parking_slot():
    this_user = User.query.filter_by(is_admin=True).first()
    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']
        pin_code = request.form['pincode']
        price = request.form['price']
        total_spots = int(request.form['total_spots'])
        new_parking_lot = ParkingLot(
            prime_location_name=name,
            address=location,
            pin_code=pin_code,
            price=price,
            maximum_number_of_spots=total_spots
        )
        db.session.add(new_parking_lot)
        db.session.commit()
        for i in range(total_spots):
            spot = ParkingSpot(
                lot_id=new_parking_lot.id,
                status='A' 
            )
            db.session.add(spot)
        db.session.commit()
        return redirect(url_for('admin_dashboard'))
    return render_template('admin.html')

from sqlalchemy.orm import joinedload
@app.route('/user-dashboard')
def user_dashboard():
    user = User.query.filter_by(email=session['user_email']).first()

    current_reservations = Reservation.query.filter_by(user_id=user.id, leaving_timestamp=None).all()

    past_reservations = Reservation.query.filter(Reservation.user_id == user.id,
                                                 Reservation.leaving_timestamp.isnot(None)).all()
    parking_lots = (ParkingLot.query
                    .options(joinedload(ParkingLot.spots))
                    .join(ParkingLot.spots)
                    .filter(ParkingSpot.status == 'A')
                    .group_by(ParkingLot.id)
                    .all())
    return render_template('User-dashboard.html',
                           user=user,
                           current_reservations=current_reservations,
                           past_reservations=past_reservations,
                           parking_lots=parking_lots)



@app.route('/release-spot', methods=['POST'])
def release_spot():
    reservation_id = request.form.get('reservation_id')
    if not reservation_id:
        return "Missing reservation_id!", 400
    reservation = Reservation.query.get(reservation_id)
    if not reservation:
        return "Invalid reservation ID!", 400
    
    spot = ParkingSpot.query.get(reservation.spot_id)
    if spot:
        spot.status = 'A'
    

    reservation.leaving_timestamp = datetime.utcnow()
    
    db.session.commit()
    return "Parking spot released successfully!"



@app.route('/admin-dashboard')
def admin_dashboard():
    if 'user_email' in session:
        user = User.query.filter_by(email=session['user_email']).first()
        if user and user.is_admin:
            parking_lots = ParkingLot.query.all()
            return render_template('admin-dashboard.html', parking_lots=parking_lots)
    return redirect('/login')

@app.route('/book-lot/<int:lot_id>', methods=['POST'])
def book_lot(lot_id):

    user_email = session.get('user_email')
    if not user_email:
        return "User not logged in!", 401

    user = User.query.filter_by(email=user_email).first()
    if not user:
        return "User not found!", 404

    available_spot = ParkingSpot.query.filter_by(lot_id=lot_id, status='A').first()
    if not available_spot:
        return "No available spots in this parking lot.", 400


    reservation = Reservation(
        spot_id=available_spot.id,
        user_id=user.id,
        parking_timestamp=datetime.utcnow()
    )
    available_spot.status = 'O'

    db.session.add(reservation)
    db.session.commit()

    return "Your parking spot has been reserved.", 200


@app.route('/logout')
def logout():
    session.pop('user_email', None)
    return redirect('/login')

@app.route('/delete_lot/<int:lot_id>', methods=['POST'])
def delete_lot(lot_id):
    lot = ParkingLot.query.get_or_404(lot_id)
    reservations_count = Reservation.query.join(ParkingSpot).filter(ParkingSpot.lot_id == lot_id).count()
    if reservations_count > 0:
        flash("Cannot delete parking lot: some spots have existing reservations.", "danger")
        return redirect(url_for('admin_dashboard'))
    occupied_spots = ParkingSpot.query.filter_by(lot_id=lot_id, status='O').count()
    if occupied_spots > 0:
        flash("Cannot delete parking lot because some spots are occupied.", "danger")
        return redirect(url_for('admin_dashboard'))
    spots = ParkingSpot.query.filter_by(lot_id=lot_id).all()
    for spot in spots:
        db.session.delete(spot)
    db.session.delete(lot)
    db.session.commit()
    flash(f'Parking lot "{lot.prime_location_name}" and its spots have been deleted.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/edit_lot/<int:lot_id>', methods=['GET', 'POST'])
def edit_lot(lot_id):
    lot = ParkingLot.query.get_or_404(lot_id)
    if request.method == 'POST':
        try:
            max_spots = int(request.form['max_spots'])
            if max_spots < 0:
                flash("Number of spots must be positive.", "danger")
            else:
                current_spots = ParkingSpot.query.filter_by(lot_id=lot_id).all()
                current_count = len(current_spots)
                available_spots = [s for s in current_spots if s.status == 'A']

                if max_spots < current_count:
                    to_remove = current_count - max_spots
                    if to_remove > len(available_spots):
                        flash(
                            f"Cannot decrease spots: only {len(available_spots)} available, but need to remove {to_remove}. Remove reservations or release occupied spots first.",
                            "danger")
                        return render_template('edit_lot.html', lot=lot)
                
                    for spot in available_spots[:to_remove]:
                        db.session.delete(spot)
                elif max_spots > current_count:
                    to_add = max_spots - current_count
                    for _ in range(to_add):
                        db.session.add(ParkingSpot(lot_id=lot_id, status='A'))
           
                lot.maximum_number_of_spots = max_spots
                db.session.commit()
                flash("Parking lot updated successfully!", "success")
                return redirect(url_for('admin_dashboard'))
        except ValueError:
            flash("Please enter a valid integer.", "danger")
    return render_template('edit_lot.html', lot=lot)



@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/admin/users')
def admin_view_users():
    

    if 'user_email' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))
    
    user = User.query.filter_by(email=session['user_email']).first()
    if not user or not user.is_admin:
        flash("You do not have permission to access this page.", "danger")
        return redirect(url_for('login'))
    
    all_users = User.query.all()
    return render_template('admin-users.html', users=all_users)

@app.route('/admin/summary')
def admin_summary():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    user = User.query.filter_by(email=session['user_email']).first()
    if not user or not user.is_admin:
        flash("Access denied.", "danger")
        return redirect(url_for('login'))

    total_lots = ParkingLot.query.count()
    total_spots = ParkingSpot.query.count()
    available_spots = ParkingSpot.query.filter_by(status='A').count()
    occupied_spots = ParkingSpot.query.filter_by(status='O').count()
    total_users = User.query.count()

    parking_lots = ParkingLot.query.all()
    lots_info = []
    for lot in parking_lots:
        total = len(lot.spots)
        available = sum(1 for spot in lot.spots if spot.status == 'A')
        occupied = total - available
        lots_info.append({
            'name': lot.prime_location_name,
            'total_spots': total,
            'available_spots': available,
            'occupied_spots': occupied
        })

    recent_reservations = Reservation.query.order_by(Reservation.parking_timestamp.desc()).limit(10).all()


    lot_names = [lot['name'] for lot in lots_info]
    occupied_counts = [lot['occupied_spots'] for lot in lots_info]
    available_counts = [lot['available_spots'] for lot in lots_info]


    plt.figure(figsize=(10,6))
    bar_width = 0.4
    indices = range(len(lot_names))

    plt.bar(indices, occupied_counts, bar_width, label='Occupied', color='salmon')
    plt.bar([i + bar_width for i in indices], available_counts, bar_width, label='Available', color='lightgreen')
    plt.xlabel('Parking Lots')
    plt.ylabel('Number of Spots')
    plt.title('Parking Spots Occupied vs Available per Lot')
    plt.xticks([i + bar_width/2 for i in indices], lot_names, rotation=45, ha='right')
    plt.legend()
    plt.tight_layout()

    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plot_data = base64.b64encode(img.getvalue()).decode()
    plt.close()

    return render_template('admin-summary.html',
                           total_lots=total_lots,
                           total_spots=total_spots,
                           available_spots=available_spots,
                           occupied_spots=occupied_spots,
                           total_users=total_users,
                           lots_info=lots_info,
                           recent_reservations=recent_reservations,
                           plot_data=plot_data)

@app.route('/user/summary')
def user_summary():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    user = User.query.filter_by(email=session['user_email']).first()
    if not user:
        return redirect(url_for('login'))

    reservations = Reservation.query.filter_by(user_id=user.id).order_by(Reservation.parking_timestamp.desc()).all()
    current_reservations = [r for r in reservations if r.leaving_timestamp is None]
    past_reservations = [r for r in reservations if r.leaving_timestamp is not None]

    total_sessions = len(reservations)
    total_duration = 0
    total_cost = 0


    monthly_sessions = defaultdict(int)
    for r in past_reservations:
        month = r.parking_timestamp.month
        monthly_sessions[month] += 1
        if r.parking_cost:
            total_cost += r.parking_cost
        duration = (r.leaving_timestamp - r.parking_timestamp).total_seconds() if r.leaving_timestamp else 0
        total_duration += duration

    total_duration_hours = total_duration / 3600

    months = [calendar.month_abbr[m] for m in sorted(monthly_sessions.keys())]
    session_counts = [monthly_sessions[m] for m in sorted(monthly_sessions.keys())] 

    plt.figure(figsize=(6,4))
    plt.bar(months, session_counts, color="skyblue")
    plt.xlabel('Month')
    plt.ylabel('Parking Sessions')
    plt.title('Parking Sessions per Month')
    plt.tight_layout()

    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plot_data = base64.b64encode(img.getvalue()).decode()
    plt.close()

    return render_template('user-summary.html',
                           user=user,
                           current_reservations=current_reservations,
                           past_reservations=past_reservations,
                           total_sessions=total_sessions,
                           total_duration_hours=total_duration_hours,
                           total_cost=total_cost,
                           plot_data=plot_data)


    for r in past_reservations:
        duration = (r.leaving_timestamp - r.parking_timestamp).total_seconds() if r.leaving_timestamp else 0
        total_duration += duration
        if r.parking_cost:
            total_cost += r.parking_cost

    total_duration_hours = total_duration / 3600

    return render_template('user-summary.html',
                           user=user,
                           current_reservations=current_reservations,
                           past_reservations=past_reservations,
                           total_sessions=total_sessions,
                           total_duration_hours=total_duration_hours,
                           total_cost=total_cost)






