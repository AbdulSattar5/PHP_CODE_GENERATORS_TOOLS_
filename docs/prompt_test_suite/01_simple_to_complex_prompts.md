# Prompt Test Suite (Simple to Complex)

Use these 20 prompts in order. They are written to match your strict schema parser format (`Table`, `File name`, `Title`, `Fields`, etc.).

## 1) Area (Basic single-table)
```text
Table: tblarea
File name: frmArea.php
Title: Area Master

Primary Key:
- Area_Code

Fields:
- Area_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- Area_Name | DB: VARCHAR(100) | Input: textbox | Required: Yes

Features: validation, keyboard
```

## 2) Class (Basic with status)
```text
Table: tblclass
File name: frmClass.php
Title: Class Master

Primary Key:
- Class_Code

Fields:
- Class_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- Class_Name | DB: VARCHAR(100) | Input: textbox | Required: Yes
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No

Features: validation, keyboard
```

## 3) Section (Relationship dropdown)
```text
Table: tblsection
File name: frmSection.php
Title: Section Master

Primary Key:
- Section_Code

Fields:
- Section_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- Section_Name | DB: VARCHAR(100) | Input: textbox | Required: Yes
- Class_Code -> tblclass.Class_Code | Input: select | Cascade: Yes

Features: dropdown, validation, keyboard
```

## 4) Subject
```text
Table: tblsubject
File name: frmSubject.php
Title: Subject Master

Primary Key:
- Subject_Code

Fields:
- Subject_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- Subject_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Subject_Type | DB: VARCHAR(20) | Input: select | Required: Yes

Features: dropdown, validation
```

## 5) Teacher
```text
Table: tblteacher
File name: frmTeacher.php
Title: Teacher Master

Primary Key:
- Teacher_Code

Fields:
- Teacher_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- Teacher_Name | DB: VARCHAR(150) | Input: textbox | Required: Yes
- Mobile_No | DB: VARCHAR(20) | Input: textbox | Required: Yes
- Email_Address | DB: VARCHAR(120) | Input: textbox | Required: No

Features: validation, keyboard
```

## 6) Student Category
```text
Table: tblstudentcategory
File name: frmStudentCategory.php
Title: Student Category Master

Primary Key:
- Category_Code

Fields:
- Category_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- Category_Name | DB: VARCHAR(100) | Input: textbox | Required: Yes
- Discount_Percent | DB: DECIMAL(5,2) | Input: textbox | Required: No
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No

Features: validation, keyboard
```

## 7) Fee Head (Relationship + dependency)
```text
Table: tblfeehead
File name: frmFeeHead.php
Title: Fee Head Master

Primary Key:
- FeeHead_Code

Fields:
- FeeHead_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- FeeHead_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Ledger_Code -> tblchartofaccounts.Ledger_Code | Input: select | Cascade: No
- Is_Monthly | DB: TINYINT(1) | Input: checkbox | Required: No

Dependencies:
- tblfeevoucherdt | field=FeeHead_Code | message=Cannot delete fee head because voucher detail exists

Features: dropdown, validation, predelete
```

## 8) Academic Session
```text
Table: tblsession
File name: frmSession.php
Title: Session Master

Primary Key:
- Session_Code

Fields:
- Session_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- Session_Title | DB: VARCHAR(50) | Input: textbox | Required: Yes
- Date_From | DB: DATE | Input: date | Required: Yes
- Date_To | DB: DATE | Input: date | Required: Yes
- Is_Current | DB: TINYINT(1) | Input: checkbox | Required: No

Features: validation, keyboard
```

## 9) Campus
```text
Table: tblcampus
File name: frmCampus.php
Title: Campus Master

Primary Key:
- Campus_Code

Fields:
- Campus_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- Campus_Name | DB: VARCHAR(150) | Input: textbox | Required: Yes
- City_Name | DB: VARCHAR(80) | Input: textbox | Required: Yes
- Phone_No | DB: VARCHAR(25) | Input: textbox | Required: No

Features: validation, keyboard
```

## 10) Employee (Dependency heavy)
```text
Table: tblemployee
File name: frmEmployee.php
Title: Employee Master

Primary Key:
- Employee_Code

Fields:
- Employee_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- Employee_Name | DB: VARCHAR(150) | Input: textbox | Required: Yes
- Department_Code -> tbldepartment.Department_Code | Input: select | Cascade: No
- Designation_Code -> tbldesignation.Designation_Code | Input: select | Cascade: No
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No

Dependencies:
- tblpayroll | field=Employee_Code | message=Cannot delete employee with payroll records
- tblattendance | field=Employee_Code | message=Cannot delete employee with attendance records

Features: dropdown, validation, keyboard, predelete
```

## 11) Class Section Mapping (Multi-relationship)
```text
Table: tblclasssection
File name: frmClassSection.php
Title: Class Section Mapping

Primary Key:
- Mapping_Code

Fields:
- Mapping_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- Campus_Code -> tblcampus.Campus_Code | Input: select | Cascade: No
- Class_Code -> tblclass.Class_Code | Input: select | Cascade: No
- Section_Code -> tblsection.Section_Code | Input: select | Cascade: No
- Capacity | DB: INT | Input: textbox | Required: No

Features: dropdown, validation, keyboard
```

## 12) Timetable Slot
```text
Table: tbltimetableslot
File name: frmTimetableSlot.php
Title: Timetable Slot

Primary Key:
- Slot_Code

Fields:
- Slot_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- ClassSection_Code -> tblclasssection.Mapping_Code | Input: select | Cascade: No
- Subject_Code -> tblsubject.Subject_Code | Input: select | Cascade: No
- Teacher_Code -> tblteacher.Teacher_Code | Input: select | Cascade: No
- Day_Name | DB: VARCHAR(20) | Input: select | Required: Yes
- Period_No | DB: INT | Input: textbox | Required: Yes
- Time_From | DB: TIME | Input: time | Required: Yes
- Time_To | DB: TIME | Input: time | Required: Yes

Features: dropdown, validation, keyboard
```

## 13) Transport Route
```text
Table: tbltransportroute
File name: frmTransportRoute.php
Title: Transport Route

Primary Key:
- Route_Code

Fields:
- Route_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- Route_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Start_Point | DB: VARCHAR(120) | Input: textbox | Required: Yes
- End_Point | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Route_Fare | DB: DECIMAL(10,2) | Input: textbox | Required: Yes
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No

Features: validation, keyboard
```

## 14) Examination Type
```text
Table: tblexamtype
File name: frmExamType.php
Title: Exam Type Master

Primary Key:
- ExamType_Code

Fields:
- ExamType_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- ExamType_Name | DB: VARCHAR(100) | Input: textbox | Required: Yes
- Weightage_Percent | DB: DECIMAL(5,2) | Input: textbox | Required: No

Dependencies:
- tblexamsetup | field=ExamType_Code | message=Cannot delete exam type linked in exam setup

Features: validation, predelete
```

## 15) Student House
```text
Table: tblstudenthouse
File name: frmStudentHouse.php
Title: Student House Master

Primary Key:
- House_Code

Fields:
- House_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- House_Name | DB: VARCHAR(100) | Input: textbox | Required: Yes
- House_Color | DB: VARCHAR(30) | Input: textbox | Required: No
- House_Captain | DB: VARCHAR(120) | Input: textbox | Required: No

Features: validation, keyboard
```

## 16) Student Master-Detail (Core ERP scenario)
```text
Master Table: tblstudent
Detail Table: tblstudentsubjectdt
File name: frmStudent.php
Title: Student Master

Primary Key:
- STU_CODE

Master Fields:
- STU_CODE | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- AdmissionNo | DB: VARCHAR(30) | Input: textbox | Required: Yes
- Campus_Code -> tblcampus.Campus_Code | Input: select | Cascade: No
- Class_Code -> tblclass.Class_Code | Input: select | Cascade: No
- Section_Code -> tblsection.Section_Code | Input: select | Cascade: No
- Student_Name | DB: VARCHAR(150) | Input: textbox | Required: Yes
- Father_Name | DB: VARCHAR(150) | Input: textbox | Required: Yes
- DOB | DB: DATE | Input: date | Required: Yes
- Status | DB: TINYINT(1) | Input: checkbox | Required: No

Detail Grid (tblstudentsubjectdt):
- SR_NO | DB: INT | Input: textbox | Required: Yes | Readonly: Yes
- Subject_Code -> tblsubject.Subject_Code | Input: select | Cascade: No
- Subject_Name | DB: VARCHAR(120) | Input: textbox | Required: No | Readonly: Yes
- Is_Optional | DB: TINYINT(1) | Input: checkbox | Required: No

Dependencies:
- tblattendance | field=STU_CODE | message=Cannot delete student with attendance records
- tblstudentfee | field=STU_CODE | message=Cannot delete student with fee records

Features: dropdown, validation, keyboard, predelete
```

## 17) Fee Voucher Master-Detail
```text
Master Table: tblfeevoucher
Detail Table: tblfeevoucherdt
File name: frmFeeVoucher.php
Title: Fee Voucher

Primary Key:
- Voucher_Code

Master Fields:
- Voucher_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- Voucher_Date | DB: DATE | Input: date | Required: Yes
- Campus_Code -> tblcampus.Campus_Code | Input: select | Cascade: No
- STU_CODE -> tblstudent.STU_CODE | Input: select | Cascade: No
- Remarks | DB: VARCHAR(250) | Input: textbox | Required: No

Detail Grid (tblfeevoucherdt):
- SR_NO | DB: INT | Input: textbox | Required: Yes | Readonly: Yes
- FeeHead_Code -> tblfeehead.FeeHead_Code | Input: select | Cascade: No
- Amount | DB: DECIMAL(12,2) | Input: textbox | Required: Yes
- Discount | DB: DECIMAL(12,2) | Input: textbox | Required: No
- Net_Amount | DB: DECIMAL(12,2) | Input: textbox | Required: Yes | Readonly: Yes

Features: dropdown, validation, keyboard
```

## 18) Purchase Order Master-Detail
```text
Master Table: tblpurchaseorder
Detail Table: tblpurchaseorderdt
File name: frmPurchaseOrder.php
Title: Purchase Order

Primary Key:
- PO_Code

Master Fields:
- PO_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- PO_Date | DB: DATE | Input: date | Required: Yes
- Vendor_Code -> tblvendor.Vendor_Code | Input: select | Cascade: No
- Campus_Code -> tblcampus.Campus_Code | Input: select | Cascade: No
- Notes | DB: VARCHAR(250) | Input: textbox | Required: No

Detail Grid (tblpurchaseorderdt):
- SR_NO | DB: INT | Input: textbox | Required: Yes | Readonly: Yes
- Item_Code -> tblitem.Item_Code | Input: select | Cascade: No
- Qty | DB: DECIMAL(12,2) | Input: textbox | Required: Yes
- Rate | DB: DECIMAL(12,2) | Input: textbox | Required: Yes
- Amount | DB: DECIMAL(12,2) | Input: textbox | Required: Yes | Readonly: Yes

Features: dropdown, validation, keyboard, predelete
```

## 19) Stress Prompt (High field count + multiple patterns)
```text
Table: tbladmissioninquiry
File name: frmAdmissionInquiry.php
Title: Admission Inquiry

Primary Key:
- Inquiry_Code

Fields:
- Inquiry_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes | Readonly: Yes
- Inquiry_Date | DB: DATE | Input: date | Required: Yes
- Student_Name | DB: VARCHAR(150) | Input: textbox | Required: Yes
- Father_Name | DB: VARCHAR(150) | Input: textbox | Required: Yes
- Mobile_No | DB: VARCHAR(20) | Input: textbox | Required: Yes
- Class_Code -> tblclass.Class_Code | Input: select | Cascade: No
- Section_Code -> tblsection.Section_Code | Input: select | Cascade: No
- Campus_Code -> tblcampus.Campus_Code | Input: select | Cascade: No
- Source_Code -> tblinquirysource.Source_Code | Input: select | Cascade: No
- Followup_Date | DB: DATE | Input: date | Required: No
- Status_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Remarks | DB: VARCHAR(300) | Input: textbox | Required: No

Features: dropdown, validation, keyboard, predelete
```

## 20) Negative Guardrail Test (Expected rejection)
```text
Create a modern student dashboard form with cards, graphs, and filters.
Add all useful fields and generate complete production code.
```

Expected result for prompt 20 in strict mode: parser contract rejection (`422`) because required canonical sections are missing.
