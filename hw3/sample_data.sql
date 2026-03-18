-- Sample flight data for testing

-- Insert sample flights
INSERT INTO flights (flight_number, airline, origin, destination, departure_time, arrival_time, total_seats, available_seats, price, status, created_at, updated_at)
VALUES
    ('SU1234', 'Aeroflot', 'SVO', 'LED', '2026-04-01 10:00:00', '2026-04-01 12:00:00', 100, 100, 5000.0, 'SCHEDULED', NOW(), NOW()),
    ('SU5678', 'Aeroflot', 'LED', 'SVO', '2026-04-01 15:00:00', '2026-04-01 17:00:00', 100, 95, 5500.0, 'SCHEDULED', NOW(), NOW()),
    ('S71234', 'S7 Airlines', 'VKO', 'AER', '2026-04-02 08:00:00', '2026-04-02 11:00:00', 150, 150, 8000.0, 'SCHEDULED', NOW(), NOW()),
    ('S75678', 'S7 Airlines', 'AER', 'VKO', '2026-04-02 18:00:00', '2026-04-02 21:00:00', 150, 140, 8500.0, 'SCHEDULED', NOW(), NOW()),
    ('UT1001', 'UTair', 'DME', 'KZN', '2026-04-03 09:00:00', '2026-04-03 11:30:00', 80, 80, 4000.0, 'SCHEDULED', NOW(), NOW()),
    ('UT1002', 'UTair', 'KZN', 'DME', '2026-04-03 16:00:00', '2026-04-03 18:30:00', 80, 75, 4200.0, 'SCHEDULED', NOW(), NOW()),
    ('SU9999', 'Aeroflot', 'SVO', 'VVO', '2026-04-05 06:00:00', '2026-04-05 15:00:00', 200, 200, 25000.0, 'SCHEDULED', NOW(), NOW()),
    ('FV1111', 'Rossiya Airlines', 'LED', 'KRR', '2026-04-06 12:00:00', '2026-04-06 15:30:00', 120, 110, 7000.0, 'SCHEDULED', NOW(), NOW());

-- Note: Sample reservations would be created through the API when bookings are made
