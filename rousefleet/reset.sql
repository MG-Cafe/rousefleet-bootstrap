-- Reset script for Rouse FleetPro Spanner Database

-- Drop Indexes first
DROP INDEX IF EXISTS EquipmentBySerialNumber;
DROP INDEX IF EXISTS EquipmentByCategoryMakeModel;
DROP INDEX IF EXISTS EquipmentByLocation;
DROP INDEX IF EXISTS EquipmentByCurrentServiceLocation;
DROP INDEX IF EXISTS EquipmentByCurrentCustomer;
DROP INDEX IF EXISTS Equipment_serial_number_key; -- This was a UNIQUE INDEX

DROP INDEX IF EXISTS MaintenanceJobByEquipment;
DROP INDEX IF EXISTS MaintenanceJobByDate;

DROP INDEX IF EXISTS CustomerByName;

DROP INDEX IF EXISTS CustomerEquipmentAssignmentByCustomerEquipment;
DROP INDEX IF EXISTS CustomerEquipmentAssignmentByEquipment;

-- Drop the Property Graph
DROP PROPERTY GRAPH IF EXISTS FleetGraph;

-- Drop Tables in an order that respects foreign key constraints
-- (Child tables or tables with foreign keys are dropped before the tables they reference)

-- 1. MaintenanceJob has a FOREIGN KEY to Equipment
DROP TABLE IF EXISTS MaintenanceJob;

-- 2. CustomerEquipmentAssignment has FOREIGN KEYs to Customer and Equipment
DROP TABLE IF EXISTS CustomerEquipmentAssignment;

-- 3. Equipment has FOREIGN KEYs to ServiceLocation and Customer
--    It is also referenced by MaintenanceJob and CustomerEquipmentAssignment, which are now dropped.
DROP TABLE IF EXISTS Equipment;

-- 4. Customer is referenced by Equipment and CustomerEquipmentAssignment (now dropped)
DROP TABLE IF EXISTS Customer;

-- 5. ServiceLocation is referenced by Equipment (now dropped)
DROP TABLE IF EXISTS ServiceLocation;

-- All FleetPro specific schema elements should now be removed.
-- You can re-run your setup.py script to recreate the schema and load data.