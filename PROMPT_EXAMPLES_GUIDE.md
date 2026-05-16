# PHP Form Generation Prompt Examples Guide (Strict Parser Safe)

This guide gives parser-safe prompt formats for ERP PHP generation.

## 1. General Prompt (Use This First)

Use this template for best success rate.

```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete [Entity] [master/master-detail] form.

Master Table: [tbl...]
Detail Table: [tbl...]                 # only for master-detail
File name: [frmXxx.php]
Title: [Form Title]
CaseType: [CaseType]
Primary Key: [Field_Name]
Foreign Key: [Field_Name]              # only for master-detail

Master Fields:
- Field_Name | DB: TYPE | Input: textbox/select/date/checkbox/readonly numeric | Required: Yes/No
- ...

Detail Fields:                          # ONLY this heading (not "Detail Grid Fields")
- Field_Name | DB: TYPE | Input: select/numeric/readonly/hidden | Required: Yes/No
- ...

Relationships:                          # optional
- tblchild.FK_Field -> tblmaster.PK_Field

Cascading Dropdowns:                    # optional
- When [Field] changes -> [action]

Calculations:                           # optional
- [Formula]

Grid Operations:                        # optional (for master-detail)
- Add row
- Edit row
- Delete row
- Validate: At least 1 detail row required

Dependencies (Pre-Delete Checks):       # optional
- tblx | field=Field_Name | message=Cannot delete. Related records exist.

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
- funStartTran, funEndTran
- AJAX GetMaxID handler + maxid()
- formValidation
- checkKeycode
```

## 2. Prompt Rules (Important)

1. Always write `Master Fields:` exactly.
2. For master-detail, write `Detail Fields:` exactly.
3. Do not use `Detail Grid Fields:` (can fail strict parsing).
4. Keep field lines in bullet format: `- Name | DB: ... | Input: ... | Required: ...`
5. If no detail section, write `Detail Grid: Not required`.
6. Mention dependencies and required company patterns explicitly.

---

## 3. SIMPLE Prompts (4 Examples)

### Example 1 - Area Master
```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete Area master form.

Master Table: tblarea
File name: frmArea.php
Title: Area
CaseType: Area
Primary Key: Area_Code

Master Fields:
- Area_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- Area_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No

Detail Grid: Not required

Dependencies (Pre-Delete Checks):
- tblcustomer | field=Area_Code | message=Cannot delete. Customer records exist.

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
- AJAX GetMaxID handler + maxid()
- formValidation
```

### Example 2 - Department Master
```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete Department master form.

Master Table: tbldepartment
File name: frmDepartment.php
Title: Department
CaseType: Department
Primary Key: Department_Code

Master Fields:
- Department_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- Department_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Sort_Order | DB: INT | Input: numeric | Required: No
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No

Detail Grid: Not required

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord
- AJAX GetMaxID handler + maxid()
- formValidation
```

### Example 3 - Cost Center Master
```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete Cost Center master form.

Master Table: tblcostcenter
File name: frmCostCenter.php
Title: Cost Center
CaseType: CostCenter
Primary Key: CostCenter_Code

Master Fields:
- CostCenter_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- CostCenter_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Remarks | DB: VARCHAR(200) | Input: textbox | Required: No
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No

Detail Grid: Not required

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord
- AJAX GetMaxID handler + maxid()
- formValidation
```

### Example 4 - School Master
```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete School master form.

Master Table: tblschool
File name: frmSchool.php
Title: School
CaseType: School
Primary Key: School_Code

Master Fields:
- School_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- School_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- City_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Address | DB: VARCHAR(200) | Input: textbox | Required: No
- Phone_No | DB: VARCHAR(20) | Input: textbox | Required: No
- Email | DB: VARCHAR(120) | Input: textbox | Required: No
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No

Detail Grid: Not required

Dependencies (Pre-Delete Checks):
- tblstudent | field=School_Code | message=Cannot delete. Student records exist.

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
- funStartTran, funEndTran
- AJAX GetMaxID handler + maxid()
- formValidation
- checkKeycode
```

---

## 4. MEDIUM Prompts (3 Examples)

### Example 1 - Sub Area with Dropdown + Validation
```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete Sub Area master form.

Master Table: tblsubarea
File name: frmSubArea.php
Title: Sub Area
CaseType: SubArea
Primary Key: SubArea_Code

Master Fields:
- SubArea_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- Area_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- SubArea_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: Yes

Relationships:
- tblsubarea.Area_Code -> tblarea.Area_Code

Business Validations:
- SubArea_Name must be unique within Area_Code

Detail Grid: Not required

Dependencies (Pre-Delete Checks):
- tblcustomer | field=SubArea_Code | message=Cannot delete. Customer records exist.

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows
- AJAX GetMaxID handler + maxid()
- formValidation
- checkKeycode
```

### Example 2 - Employee with Department/Designation
```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete Employee master form.

Master Table: tblemployee
File name: frmEmployee.php
Title: Employee
CaseType: Employee
Primary Key: Employee_Code

Master Fields:
- Employee_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- Employee_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Department_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Designation_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Email | DB: VARCHAR(100) | Input: textbox | Required: No
- Contact_No | DB: VARCHAR(20) | Input: textbox | Required: No
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No

Cascading Dropdowns:
- When Department_Code changes -> filter Designation_Code by Department_Code

Business Validations:
- Email should be unique if provided

Detail Grid: Not required

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord
- AJAX GetMaxID handler + maxid()
- formValidation
- Select2 event handlers
```

### Example 3 - Item with Group/Subgroup Cascade
```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete Item master form.

Master Table: tblitem
File name: frmItem.php
Title: Item
CaseType: Item
Primary Key: Item_Code

Master Fields:
- Item_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- Item_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Group_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- SubGroup_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Unit_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Sale_Rate | DB: DECIMAL(10,2) | Input: numeric | Required: Yes
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No

Cascading Dropdowns:
- When Group_Code changes -> filter SubGroup_Code by Group_Code

Detail Grid: Not required

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord
- AJAX GetMaxID handler + maxid()
- formValidation
- Select2 event handlers
```

---

## 5. HARD Prompts (3 Examples)

### Example 1 - Invoice Master-Detail
```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete Invoice master-detail form.

Master Table: tblinvoice
Detail Table: tblinvoicedetail
File name: frmInvoice.php
Title: Sales Invoice
CaseType: Invoice
Primary Key: Invoice_No
Foreign Key: Invoice_No

Master Fields:
- Invoice_No | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- Invoice_Date | DB: DATE | Input: datepicker | Required: Yes
- Customer_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Salesman_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Total_Amount | DB: DECIMAL(12,2) | Input: readonly numeric | Required: No
- Discount_Percent | DB: DECIMAL(5,2) | Input: numeric | Required: No
- Net_Amount | DB: DECIMAL(12,2) | Input: readonly numeric | Required: No
- Remarks | DB: VARCHAR(200) | Input: textbox | Required: No

Detail Fields:
- Invoice_No | DB: VARCHAR(20) | Input: hidden | Required: Yes
- Sr_No | DB: INT | Input: readonly | Required: Yes
- Product_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Product_Name | DB: VARCHAR(120) | Input: readonly | Required: No
- Quantity | DB: DECIMAL(10,2) | Input: numeric | Required: Yes
- Rate | DB: DECIMAL(10,2) | Input: numeric | Required: Yes
- Amount | DB: DECIMAL(12,2) | Input: readonly | Required: No

Relationships:
- tblinvoicedetail.Invoice_No -> tblinvoice.Invoice_No

Cascading Dropdowns:
- When Customer_Code changes -> filter Salesman_Code by customer area
- When Product_Code changes -> auto-fill Product_Name and Rate

Calculations:
- Detail Amount = Quantity * Rate
- Master Total_Amount = SUM(Detail.Amount)
- Master Net_Amount = Total_Amount - (Total_Amount * Discount_Percent / 100)

Grid Operations:
- Add row
- Edit row
- Delete row
- Validate: At least 1 detail row required

Dependencies (Pre-Delete Checks):
- tblpayment | field=Invoice_No | message=Cannot delete. Payment records exist.
- tbldelivery | field=Invoice_No | message=Cannot delete. Delivery records exist.

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
- funStartTran, funEndTran
- AJAX GetMaxID handler + maxid()
- formValidation
- Grid add/edit/delete
- Select2 event handlers
```

### Example 2 - Purchase Order Master-Detail
```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete Purchase Order master-detail form.

Master Table: tblpurchaseorder
Detail Table: tblpurchaseorderdetail
File name: frmPurchaseOrder.php
Title: Purchase Order
CaseType: PurchaseOrder
Primary Key: PO_No
Foreign Key: PO_No

Master Fields:
- PO_No | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- PO_Date | DB: DATE | Input: datepicker | Required: Yes
- Supplier_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Delivery_Date | DB: DATE | Input: datepicker | Required: Yes
- Total_Amount | DB: DECIMAL(12,2) | Input: readonly numeric | Required: No
- Status | DB: VARCHAR(20) | Input: select | Required: Yes

Detail Fields:
- PO_No | DB: VARCHAR(20) | Input: hidden | Required: Yes
- Sr_No | DB: INT | Input: readonly | Required: Yes
- Product_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Product_Name | DB: VARCHAR(120) | Input: readonly | Required: No
- Quantity | DB: DECIMAL(10,2) | Input: numeric | Required: Yes
- Unit_Price | DB: DECIMAL(10,2) | Input: numeric | Required: Yes
- Amount | DB: DECIMAL(12,2) | Input: readonly | Required: No

Relationships:
- tblpurchaseorderdetail.PO_No -> tblpurchaseorder.PO_No

Calculations:
- Detail Amount = Quantity * Unit_Price
- Master Total_Amount = SUM(Detail.Amount)

Grid Operations:
- Add row
- Edit row
- Delete row
- Validate: At least 1 detail row required

Dependencies (Pre-Delete Checks):
- tblgoodsreceipt | field=PO_No | message=Cannot delete. Goods receipt exists.

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows
- funStartTran, funEndTran
- AJAX GetMaxID handler + maxid()
- formValidation
```

### Example 3 - Student Master-Detail
```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete Student master-detail form.

Master Table: tblstudent
Detail Table: tblstudentdetail
File name: frmStudent.php
Title: Student
CaseType: Student
Primary Key: Student_Code
Foreign Key: Student_Code

Master Fields:
- Student_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- Student_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Class_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Section_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Admission_Date | DB: DATE | Input: datepicker | Required: Yes
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No

Detail Fields:
- Student_Code | DB: VARCHAR(20) | Input: hidden | Required: Yes
- Sr_No | DB: INT | Input: readonly | Required: Yes
- Subject_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Marks | DB: DECIMAL(5,2) | Input: numeric | Required: No

Relationships:
- tblstudentdetail.Student_Code -> tblstudent.Student_Code

Grid Operations:
- Add row
- Edit row
- Delete row
- Validate: At least 1 detail row required

Dependencies (Pre-Delete Checks):
- tblattendance | field=Student_Code | message=Cannot delete. Attendance records exist.

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows
- funStartTran, funEndTran
- AJAX GetMaxID handler + maxid()
- formValidation
- TXTCOUNTACC-based detail loop
```

---

## 6. COMPLEX Prompts (3 Examples)

### Example 1 - Sales Order with Approval Workflow
```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete Sales Order master-detail form with approval workflow.

Master Table: tblsalesorder
Detail Table: tblsalesorderdetail
File name: frmSalesOrder.php
Title: Sales Order
CaseType: SalesOrder
Primary Key: SO_No
Foreign Key: SO_No

Master Fields:
- SO_No | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- SO_Date | DB: DATE | Input: datepicker | Required: Yes
- Customer_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Salesman_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Status | DB: VARCHAR(20) | Input: readonly | Required: Yes
- Net_Amount | DB: DECIMAL(12,2) | Input: readonly numeric | Required: No

Detail Fields:
- SO_No | DB: VARCHAR(20) | Input: hidden | Required: Yes
- Sr_No | DB: INT | Input: readonly | Required: Yes
- Product_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Quantity | DB: DECIMAL(10,2) | Input: numeric | Required: Yes
- Rate | DB: DECIMAL(10,2) | Input: numeric | Required: Yes
- Amount | DB: DECIMAL(12,2) | Input: readonly | Required: No

Calculations:
- Detail Amount = Quantity * Rate
- Master Net_Amount = SUM(Detail.Amount)

Business Validations:
- If customer credit limit exceeded, status should become Pending Approval

Dependencies (Pre-Delete Checks):
- tblinvoice | field=SO_No | message=Cannot delete. Invoice exists.
- tbldelivery | field=SO_No | message=Cannot delete. Delivery exists.

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
- funStartTran, funEndTran
- AJAX GetMaxID handler + maxid()
- formValidation
- Grid add/edit/delete
- Approval status flow
```

### Example 2 - Production Order with BOM
```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete Production Order form with BOM detail.

Master Table: tblproductionorder
Detail Table: tblproductionorderdetail
File name: frmProductionOrder.php
Title: Production Order
CaseType: ProductionOrder
Primary Key: PO_No
Foreign Key: PO_No

Master Fields:
- PO_No | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- PO_Date | DB: DATE | Input: datepicker | Required: Yes
- Production_Date | DB: DATE | Input: datepicker | Required: Yes
- Supervisor_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Total_Cost | DB: DECIMAL(12,2) | Input: readonly numeric | Required: No
- Status | DB: VARCHAR(20) | Input: select | Required: Yes

Detail Fields:
- PO_No | DB: VARCHAR(20) | Input: hidden | Required: Yes
- Sr_No | DB: INT | Input: readonly | Required: Yes
- Product_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Quantity_To_Produce | DB: DECIMAL(10,2) | Input: numeric | Required: Yes
- Unit_Cost | DB: DECIMAL(10,2) | Input: readonly | Required: No
- Amount | DB: DECIMAL(12,2) | Input: readonly | Required: No

Calculations:
- Amount = Quantity_To_Produce * Unit_Cost
- Master Total_Cost = SUM(Detail.Amount)

Business Validations:
- Check stock availability for BOM raw materials before save

Dependencies (Pre-Delete Checks):
- tblstockmovement | field=PO_No | message=Cannot delete. Stock movement exists.

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows
- funStartTran, funEndTran
- AJAX GetMaxID handler + maxid()
- formValidation
- Grid add/edit/delete
```

### Example 3 - Service Contract with Milestone Billing
```text
STRICT MODE. NO GENERIC FALLBACK OUTPUT.

Create complete Service Contract master-detail form with milestone billing.

Master Table: tblservicecontract
Detail Table: tblservicecontractmilestone
File name: frmServiceContract.php
Title: Service Contract
CaseType: ServiceContract
Primary Key: Contract_No
Foreign Key: Contract_No

Master Fields:
- Contract_No | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- Contract_Date | DB: DATE | Input: datepicker | Required: Yes
- Customer_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Start_Date | DB: DATE | Input: datepicker | Required: Yes
- End_Date | DB: DATE | Input: datepicker | Required: Yes
- Contract_Value | DB: DECIMAL(12,2) | Input: numeric | Required: Yes
- Net_Value | DB: DECIMAL(12,2) | Input: readonly numeric | Required: No
- Status | DB: VARCHAR(20) | Input: select | Required: Yes

Detail Fields:
- Contract_No | DB: VARCHAR(20) | Input: hidden | Required: Yes
- Sr_No | DB: INT | Input: readonly | Required: Yes
- Milestone_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Billing_Percent | DB: DECIMAL(5,2) | Input: numeric | Required: Yes
- Billing_Amount | DB: DECIMAL(12,2) | Input: readonly | Required: No
- Due_Date | DB: DATE | Input: datepicker | Required: Yes

Calculations:
- Billing_Amount = Contract_Value * Billing_Percent / 100
- Net_Value = SUM(Detail.Billing_Amount)

Business Validations:
- Sum(Billing_Percent) must be exactly 100
- End_Date must be >= Start_Date

Dependencies (Pre-Delete Checks):
- tblserviceinvoice | field=Contract_No | message=Cannot delete. Invoices already generated.

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows
- funStartTran, funEndTran
- AJAX GetMaxID handler + maxid()
- formValidation
- Grid add/edit/delete
```

---

## 7. Quick Failure Checklist (Before Sending Prompt)

1. Did you use `Master Fields:`?
2. For master-detail, did you use `Detail Fields:` (exact text)?
3. Are all key labels present (`Master Table`, `File name`, `Primary Key`)?
4. Did you avoid vague lines and provide explicit field bullets?
5. Did you include required company patterns?

If these are correct, strict generation success rate is much higher.
