"""English source text and its Thai translation, keyed by the exact English string.

`frontend/i18n.py` looks entries up as pages are rendered, so a string that is not here
is shown in English rather than left blank. Keep the keys byte-for-byte identical to the
text in the page modules, including leading and trailing spaces.

Terminology: ใบสั่งผลิต work order, หน่วยผลิต production unit, ขั้นตอน process step,
หัวหน้างาน supervisor, ผู้ว่าจ้าง contractor, รหัสเปิดใช้งาน activation code.
"""

CATALOG = {
    # ---------------------------------------------------------------- sign-in
    'Production Tracking System': {'th': 'ระบบติดตามการผลิต'},
    'Track Today. Build Tomorrow.': {'th': 'ติดตามวันนี้ สร้างพรุ่งนี้'},
    'Welcome': {'th': 'ยินดีต้อนรับ'},
    'Sign in to continue': {'th': 'เข้าสู่ระบบเพื่อดำเนินการต่อ'},
    'User Role': {'th': 'บทบาทผู้ใช้'},
    'Select role': {'th': 'เลือกบทบาท'},
    'Username': {'th': 'ชื่อผู้ใช้'},
    'Enter your username': {'th': 'กรอกชื่อผู้ใช้ของคุณ'},
    'Password': {'th': 'รหัสผ่าน'},
    'Enter your password': {'th': 'กรอกรหัสผ่านของคุณ'},
    'Sign In ': {'th': 'เข้าสู่ระบบ '},
    'First time here? ': {'th': 'เข้าใช้งานครั้งแรกใช่ไหม? '},
    'Activate your account': {'th': 'เปิดใช้งานบัญชีของคุณ'},
    ' with the code your administrator gave you.': {'th': ' ด้วยรหัสที่ผู้ดูแลระบบให้ไว้'},
    'BETTER PRODUCTION  •  HIGHER EFFICIENCY  •': {'th': 'ผลิตดีขึ้น  •  มีประสิทธิภาพสูงขึ้น  •'},
    'A STRONGER TOMORROW': {'th': 'เพื่อวันพรุ่งนี้ที่แข็งแกร่งกว่า'},
    'Industrial Terminal v2.4.1 • Station Safe-Mode Active':
        {'th': 'เทอร์มินัลอุตสาหกรรม v2.4.1 • โหมดปลอดภัยของสถานีทำงานอยู่'},
    'Please fill in all required fields.': {'th': 'กรุณากรอกข้อมูลที่จำเป็นให้ครบถ้วน'},
    'Please check your login details.': {'th': 'กรุณาตรวจสอบข้อมูลการเข้าสู่ระบบของคุณ'},
    'Could not contact the server. Please try again.':
        {'th': 'ไม่สามารถติดต่อเซิร์ฟเวอร์ได้ กรุณาลองใหม่อีกครั้ง'},
    'Invalid username or password': {'th': 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'},
    'Your account has been disabled. Please contact the administration if you think this is a mistake.':
        {'th': 'บัญชีของคุณถูกปิดใช้งาน หากคุณคิดว่าเป็นความผิดพลาด กรุณาติดต่อฝ่ายบริหาร'},
    'No access to the requested role': {'th': 'ไม่มีสิทธิ์เข้าถึงบทบาทที่ขอ'},
    'Too many login attempts': {'th': 'พยายามเข้าสู่ระบบหลายครั้งเกินไป'},
    'Authentication required': {'th': 'ต้องเข้าสู่ระบบก่อน'},
    'Logout failed. Please try again.': {'th': 'ออกจากระบบไม่สำเร็จ กรุณาลองใหม่อีกครั้ง'},

    # ------------------------------------------------------------ first sign-in
    'Set up your account.': {'th': 'ตั้งค่าบัญชีของคุณ'},
    'First sign-in': {'th': 'การเข้าสู่ระบบครั้งแรก'},
    'Enter the username and activation code your administrator gave you.':
        {'th': 'กรอกชื่อผู้ใช้และรหัสเปิดใช้งานที่ผู้ดูแลระบบให้ไว้'},
    'Activation code': {'th': 'รหัสเปิดใช้งาน'},
    'Continue': {'th': 'ดำเนินการต่อ'},
    'Choose a password': {'th': 'ตั้งรหัสผ่าน'},
    'Choose a password.': {'th': 'กรุณาตั้งรหัสผ่าน'},
    'At least 8 characters': {'th': 'อย่างน้อย 8 ตัวอักษร'},
    'Repeat password': {'th': 'กรอกรหัสผ่านอีกครั้ง'},
    'Type it again': {'th': 'พิมพ์อีกครั้ง'},
    'Check your contact details and correct them if they are wrong.':
        {'th': 'ตรวจสอบข้อมูลติดต่อของคุณ และแก้ไขหากไม่ถูกต้อง'},
    'Finish and sign in': {'th': 'เสร็จสิ้นและเข้าสู่ระบบ'},
    'Signing you in…': {'th': 'กำลังพาคุณเข้าสู่ระบบ…'},
    'The two passwords do not match.': {'th': 'รหัสผ่านทั้งสองช่องไม่ตรงกัน'},
    'Back to sign in': {'th': 'กลับไปหน้าเข้าสู่ระบบ'},
    'Your password is set. Please sign in with it.':
        {'th': 'ตั้งรหัสผ่านเรียบร้อยแล้ว กรุณาเข้าสู่ระบบด้วยรหัสผ่านนี้'},
    'That username and activation code do not match an account waiting to be set up.':
        {'th': 'ชื่อผู้ใช้และรหัสเปิดใช้งานไม่ตรงกับบัญชีที่รอการตั้งค่า'},
    'None yet. Your administrator gives you these.':
        {'th': 'ยังไม่มี ผู้ดูแลระบบจะเป็นผู้กำหนดให้คุณ'},

    # ------------------------------------------------------------- navigation
    'FLOOR OPS': {'th': 'ปฏิบัติการหน้างาน'},
    'Overview': {'th': 'ภาพรวม'},
    'Planning': {'th': 'การวางแผน'},
    'My work': {'th': 'งานของฉัน'},
    'Administration': {'th': 'การดูแลระบบ'},
    'Statistics': {'th': 'สถิติ'},
    'Profile': {'th': 'โปรไฟล์'},
    'Log out': {'th': 'ออกจากระบบ'},
    'Access denied. ': {'th': 'ไม่มีสิทธิ์เข้าถึง '},
    'Page not found. ': {'th': 'ไม่พบหน้านี้ '},
    'Return to login': {'th': 'กลับไปหน้าเข้าสู่ระบบ'},
    'Planner': {'th': 'ผู้วางแผน'},
    'Supervisor': {'th': 'หัวหน้างาน'},
    'Manager': {'th': 'ผู้จัดการ'},
    'Operations': {'th': 'ปฏิบัติการ'},
    'Operations Administrator': {'th': 'ผู้ดูแลงานปฏิบัติการ'},

    # ------------------------------------------------------- shared and errors
    'Apply': {'th': 'บันทึก'},
    'Cancel': {'th': 'ยกเลิก'},
    'Save': {'th': 'บันทึก'},
    'Remove': {'th': 'นำออก'},
    'Delete': {'th': 'ลบ'},
    'Change': {'th': 'เปลี่ยน'},
    'Yes': {'th': 'ใช่'},
    'All': {'th': 'ทั้งหมด'},
    'Unknown': {'th': 'ไม่ทราบ'},
    'N/A': {'th': 'ไม่มีข้อมูล'},
    'Never': {'th': 'ไม่เคย'},
    'Not recorded': {'th': 'ไม่ได้บันทึกไว้'},
    'Changes saved.': {'th': 'บันทึกการเปลี่ยนแปลงแล้ว'},
    'You do not have permission for this action. Contact your administrator.':
        {'th': 'คุณไม่มีสิทธิ์ดำเนินการนี้ กรุณาติดต่อผู้ดูแลระบบ'},
    'The database is unavailable or not ready. Your form has been kept; please retry.':
        {'th': 'ฐานข้อมูลไม่พร้อมใช้งาน ข้อมูลในแบบฟอร์มยังอยู่ กรุณาลองใหม่อีกครั้ง'},
    'That value is already taken. Use a different one; nothing was saved.':
        {'th': 'ค่านี้ถูกใช้ไปแล้ว กรุณาใช้ค่าอื่น ยังไม่มีการบันทึกข้อมูล'},
    'Password is too weak': {'th': 'รหัสผ่านคาดเดาได้ง่ายเกินไป'},
    'Password must be at least 8 characters long': {'th': 'รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร'},
    'Password must be at most 72 characters long': {'th': 'รหัสผ่านต้องยาวไม่เกิน 72 ตัวอักษร'},
    'Password must be a nonempty string': {'th': 'กรุณากรอกรหัสผ่าน'},
    # ------------------------------------------------------------------ profile
    'Your profile': {'th': 'โปรไฟล์ของคุณ'},
    'Your details, and the two things you can change yourself.':
        {'th': 'ข้อมูลของคุณ และสองสิ่งที่คุณเปลี่ยนเองได้'},
    'Your details': {'th': 'ข้อมูลของคุณ'},
    'Contact details': {'th': 'ข้อมูลติดต่อ'},
    'Contact details saved.': {'th': 'บันทึกข้อมูลติดต่อแล้ว'},
    'Keep these current: your email address is where account messages are sent.':
        {'th': 'โปรดปรับข้อมูลให้เป็นปัจจุบัน ระบบจะส่งข้อความเกี่ยวกับบัญชีไปยังอีเมลนี้'},
    'Change your password': {'th': 'เปลี่ยนรหัสผ่านของคุณ'},
    'Change password': {'th': 'เปลี่ยนรหัสผ่าน'},
    'Current password *': {'th': 'รหัสผ่านปัจจุบัน *'},
    'New password *': {'th': 'รหัสผ่านใหม่ *'},
    'Repeat new password *': {'th': 'กรอกรหัสผ่านใหม่อีกครั้ง *'},
    'Choose something long and unusual. Common or predictable passwords are refused.':
        {'th': 'เลือกรหัสผ่านที่ยาวและไม่ซ้ำใคร ระบบจะปฏิเสธรหัสผ่านที่เดาง่าย'},
    'Enter your current password and the new one.':
        {'th': 'กรุณากรอกรหัสผ่านปัจจุบันและรหัสผ่านใหม่'},
    'The two new passwords do not match.': {'th': 'รหัสผ่านใหม่ทั้งสองช่องไม่ตรงกัน'},
    'Your current password is not correct.': {'th': 'รหัสผ่านปัจจุบันของคุณไม่ถูกต้อง'},
    'Password changed. It applies the next time you sign in.':
        {'th': 'เปลี่ยนรหัสผ่านแล้ว จะมีผลในการเข้าสู่ระบบครั้งถัดไป'},
    'Name': {'th': 'ชื่อ'},
    'Roles': {'th': 'บทบาท'},
    'Date of birth': {'th': 'วันเกิด'},
    'Employed since': {'th': 'เริ่มงานเมื่อ'},
    'Current units': {'th': 'หน่วยผลิตปัจจุบัน'},
    'Last signed in': {'th': 'เข้าสู่ระบบล่าสุด'},
    'None assigned': {'th': 'ยังไม่ได้กำหนด'},
    ' (supervisor)': {'th': ' (หัวหน้างาน)'},
    'Email': {'th': 'อีเมล'},
    'Phone': {'th': 'โทรศัพท์'},
    'Your name, date of birth, username and roles are maintained by your administrator. '
    'Ask them if any of these is wrong.':
        {'th': 'ชื่อ วันเกิด ชื่อผู้ใช้ และบทบาทของคุณดูแลโดยผู้ดูแลระบบ '
               'หากข้อมูลใดไม่ถูกต้อง กรุณาแจ้งผู้ดูแลระบบ'},
    'That email address already belongs to another employee.':
        {'th': 'อีเมลนี้เป็นของพนักงานคนอื่นแล้ว'},

    # ------------------------------------------------------------------ planner
    'Production planning': {'th': 'การวางแผนการผลิต'},
    'Plan the next order': {'th': 'วางแผนใบสั่งผลิตถัดไป'},
    'Choose a product, review its process and schedule production.':
        {'th': 'เลือกผลิตภัณฑ์ ตรวจสอบกระบวนการ และกำหนดตารางการผลิต'},
    'New work order': {'th': 'ใบสั่งผลิตใหม่'},
    'Contractors': {'th': 'ผู้ว่าจ้าง'},
    'Unit supervisors': {'th': 'หัวหน้างานประจำหน่วยผลิต'},
    'Order details': {'th': 'รายละเอียดใบสั่งผลิต'},
    'Work order *': {'th': 'ใบสั่งผลิต *'},
    'Work order': {'th': 'ใบสั่งผลิต'},
    'Work orders': {'th': 'ใบสั่งผลิต'},
    'Contractor *': {'th': 'ผู้ว่าจ้าง *'},
    'Contractor': {'th': 'ผู้ว่าจ้าง'},
    'Search or select a contractor': {'th': 'ค้นหาหรือเลือกผู้ว่าจ้าง'},
    '+ Add a new contractor': {'th': '+ เพิ่มผู้ว่าจ้างใหม่'},
    '+ Add contractor': {'th': '+ เพิ่มผู้ว่าจ้าง'},
    'Add contractor': {'th': 'เพิ่มผู้ว่าจ้าง'},
    'Save & select': {'th': 'บันทึกและเลือก'},
    'Saved contractors are available for future orders.':
        {'th': 'ผู้ว่าจ้างที่บันทึกไว้จะใช้กับใบสั่งผลิตครั้งต่อไปได้'},
    'Contractor saved and selected for the order.':
        {'th': 'บันทึกผู้ว่าจ้างและเลือกให้กับใบสั่งผลิตนี้แล้ว'},
    'Product *': {'th': 'ผลิตภัณฑ์ *'},
    'Product': {'th': 'ผลิตภัณฑ์'},
    'Select a product': {'th': 'เลือกผลิตภัณฑ์'},
    'Production process *': {'th': 'กระบวนการผลิต *'},
    'Production process': {'th': 'กระบวนการผลิต'},
    'Select a product first': {'th': 'กรุณาเลือกผลิตภัณฑ์ก่อน'},
    'Select a product first.': {'th': 'กรุณาเลือกผลิตภัณฑ์ก่อน'},
    'Quantity *': {'th': 'จำนวน *'},
    'Start date *': {'th': 'วันที่เริ่ม *'},
    'Due date *': {'th': 'วันครบกำหนด *'},
    'Create Work Order': {'th': 'สร้างใบสั่งผลิต'},
    'Work order saved': {'th': 'บันทึกใบสั่งผลิตแล้ว'},
    'Product details': {'th': 'รายละเอียดผลิตภัณฑ์'},
    'Select a product to see its details.': {'th': 'เลือกผลิตภัณฑ์เพื่อดูรายละเอียด'},
    'Select a product and process.': {'th': 'เลือกผลิตภัณฑ์และกระบวนการ'},
    'Select an available production process.': {'th': 'เลือกกระบวนการผลิตที่ใช้งานได้'},
    'No description provided.': {'th': 'ไม่มีคำอธิบาย'},
    'Refresh catalog': {'th': 'โหลดรายการผลิตภัณฑ์ใหม่'},
    'This process is inactive.': {'th': 'กระบวนการนี้ถูกปิดใช้งาน'},
    'This process has no steps yet.': {'th': 'กระบวนการนี้ยังไม่มีขั้นตอน'},
    'Standard time unknown': {'th': 'ไม่ทราบเวลามาตรฐาน'},
    'Fill in the work order, contractor, product, process and both dates.':
        {'th': 'กรุณากรอกใบสั่งผลิต ผู้ว่าจ้าง ผลิตภัณฑ์ กระบวนการ และวันที่ทั้งสองช่อง'},
    'Enter a work order number.': {'th': 'กรุณากรอกเลขที่ใบสั่งผลิต'},
    'Select an existing contractor or save a new one first.':
        {'th': 'เลือกผู้ว่าจ้างที่มีอยู่ หรือบันทึกรายใหม่ก่อน'},
    'This work order number already exists. Use a different number. Nothing was added.':
        {'th': 'เลขที่ใบสั่งผลิตนี้มีอยู่แล้ว กรุณาใช้เลขอื่น ยังไม่มีการเพิ่มข้อมูล'},
    'No products are available yet. Ask an administrator to load the catalog.':
        {'th': 'ยังไม่มีผลิตภัณฑ์ กรุณาให้ผู้ดูแลระบบเพิ่มรายการผลิตภัณฑ์'},
    'Select a contractor to expand their details. Changes save when you click Apply.':
        {'th': 'เลือกผู้ว่าจ้างเพื่อดูรายละเอียด การเปลี่ยนแปลงจะบันทึกเมื่อกดบันทึก'},
    'Search name, email or phone': {'th': 'ค้นหาชื่อ อีเมล หรือโทรศัพท์'},
    'No contractors match.': {'th': 'ไม่พบผู้ว่าจ้างที่ตรงกัน'},
    'No contractors yet. Add your first contractor above.':
        {'th': 'ยังไม่มีผู้ว่าจ้าง เพิ่มรายแรกได้ด้านบน'},
    'No contact details yet': {'th': 'ยังไม่มีข้อมูลติดต่อ'},
    'Name *': {'th': 'ชื่อ *'},
    # --------------------------------------------------------------- supervisor
    'My process parts': {'th': 'ขั้นตอนงานของฉัน'},
    'All process parts in your production units.': {'th': 'ขั้นตอนงานทั้งหมดในหน่วยผลิตของคุณ'},
    'My units': {'th': 'หน่วยผลิตของฉัน'},
    'All production units': {'th': 'หน่วยผลิตทั้งหมด'},
    'Search order, part, description or product':
        {'th': 'ค้นหาใบสั่งผลิต ขั้นตอน คำอธิบาย หรือผลิตภัณฑ์'},
    'Select a process part': {'th': 'เลือกขั้นตอนงาน'},
    'Choose a card to see instructions and record quantities.':
        {'th': 'เลือกการ์ดเพื่อดูคำแนะนำและบันทึกจำนวน'},
    'No parts in your supervised units match these filters.':
        {'th': 'ไม่มีขั้นตอนงานในหน่วยผลิตที่คุณดูแลตรงกับตัวกรองนี้'},
    'Start': {'th': 'เริ่ม'},
    'Start pieces': {'th': 'เริ่มผลิตชิ้นงาน'},
    'Start quantity': {'th': 'จำนวนที่เริ่ม'},
    'Complete': {'th': 'เสร็จสิ้น'},
    'Complete pieces': {'th': 'ปิดงานชิ้นงาน'},
    'Complete quantity': {'th': 'จำนวนที่เสร็จ'},
    'Already prepared': {'th': 'เตรียมไว้แล้ว'},
    'Already prepared — skip pieces': {'th': 'เตรียมไว้แล้ว — ข้ามชิ้นงาน'},
    'Confirm & Update': {'th': 'ยืนยันและบันทึก'},
    'Instructions': {'th': 'คำแนะนำการทำงาน'},
    'No instructions provided.': {'th': 'ไม่มีคำแนะนำ'},
    'Notifications': {'th': 'การแจ้งเตือน'},
    'No notifications yet.': {'th': 'ยังไม่มีการแจ้งเตือน'},
    'Mark read': {'th': 'ทำเครื่องหมายว่าอ่านแล้ว'},
    'New process part in your unit': {'th': 'มีขั้นตอนงานใหม่ในหน่วยผลิตของคุณ'},
    'Ready': {'th': 'พร้อมเริ่ม'},
    'Ready to start': {'th': 'พร้อมเริ่ม'},
    'In process': {'th': 'กำลังดำเนินการ'},
    'Partial': {'th': 'บางส่วน'},
    'Partly finished': {'th': 'เสร็จบางส่วน'},
    'Finished': {'th': 'เสร็จแล้ว'},
    'Finished pieces': {'th': 'ชิ้นงานที่เสร็จแล้ว'},
    'Not finished': {'th': 'ยังไม่เสร็จ'},
    'Not started': {'th': 'ยังไม่เริ่ม'},
    'Not yet': {'th': 'ยังไม่ถึง'},
    'Waiting': {'th': 'กำลังรอ'},
    'Elapsed': {'th': 'เวลาที่ใช้ไป'},
    'Pieces': {'th': 'ชิ้นงาน'},
    ' pieces': {'th': ' ชิ้น'},
    ' pieces finished': {'th': ' ชิ้นเสร็จแล้ว'},
    ' eligible of ': {'th': ' ที่ทำได้จากทั้งหมด '},
    ' ready to start · ': {'th': ' พร้อมเริ่ม · '},
    ' running': {'th': ' กำลังทำ'},
    ' already prepared': {'th': ' เตรียมไว้แล้ว'},
    'Due ': {'th': 'ครบกำหนด '},
    'Due': {'th': 'ครบกำหนด'},
    'No due date': {'th': 'ไม่มีวันครบกำหนด'},
    'Step': {'th': 'ขั้นตอน'},
    'Step ': {'th': 'ขั้นตอน '},
    'Process': {'th': 'กระบวนการ'},
    'Process step': {'th': 'ขั้นตอนการผลิต'},
    'Process steps': {'th': 'ขั้นตอนการผลิต'},
    'No process steps': {'th': 'ไม่มีขั้นตอนการผลิต'},
    'This order has no process steps.': {'th': 'ใบสั่งผลิตนี้ไม่มีขั้นตอนการผลิต'},
    'Unit': {'th': 'หน่วยผลิต'},
    'Production unit': {'th': 'หน่วยผลิต'},
    'Production unit *': {'th': 'หน่วยผลิต *'},
    'Select a production unit': {'th': 'เลือกหน่วยผลิต'},
    'Standard': {'th': 'มาตรฐาน'},
    'Over standard': {'th': 'เกินมาตรฐาน'},
    'Over by': {'th': 'เกินไป'},

    # ------------------------------------------------------------------ manager
    'Factory overview': {'th': 'ภาพรวมโรงงาน'},
    'Manager console': {'th': 'แผงควบคุมผู้จัดการ'},
    'Choose an order to see its details and progress per process step.':
        {'th': 'เลือกใบสั่งผลิตเพื่อดูรายละเอียดและความคืบหน้าของแต่ละขั้นตอน'},
    'Search order, product or contractor': {'th': 'ค้นหาใบสั่งผลิต ผลิตภัณฑ์ หรือผู้ว่าจ้าง'},
    'Select a work order': {'th': 'เลือกใบสั่งผลิต'},
    'No work orders match this week and these filters.':
        {'th': 'ไม่มีใบสั่งผลิตที่ตรงกับสัปดาห์นี้และตัวกรองที่เลือก'},
    'No orders to show': {'th': 'ไม่มีใบสั่งผลิตให้แสดง'},
    'Open order →': {'th': 'เปิดใบสั่งผลิต →'},
    '← Back to overview': {'th': '← กลับไปหน้าภาพรวม'},
    'This work order does not exist or was cancelled.':
        {'th': 'ไม่พบใบสั่งผลิตนี้ หรือใบสั่งผลิตถูกยกเลิกแล้ว'},
    'The overview is unavailable. Retry shortly.':
        {'th': 'ไม่สามารถแสดงภาพรวมได้ กรุณาลองใหม่ในอีกสักครู่'},
    'Completed': {'th': 'เสร็จสมบูรณ์'},
    'Delayed': {'th': 'ล่าช้า'},
    'Showing ': {'th': 'กำลังแสดง '},
    ' of ': {'th': ' จาก '},
    ' to ': {'th': ' ถึง '},
    '‹ Previous week': {'th': '‹ สัปดาห์ก่อน'},
    'Next week ›': {'th': 'สัปดาห์ถัดไป ›'},
    '‹ Previous': {'th': '‹ ก่อนหน้า'},
    'Next ›': {'th': 'ถัดไป ›'},
    'Start: ': {'th': 'เริ่ม: '},
    'End': {'th': 'สิ้นสุด'},
    'Status': {'th': 'สถานะ'},
    'Product: ': {'th': 'ผลิตภัณฑ์: '},
    'Contractor: ': {'th': 'ผู้ว่าจ้าง: '},
    'No product': {'th': 'ไม่มีผลิตภัณฑ์'},
    # --------------------------------------------------------------- operations
    'Operations administration': {'th': 'การดูแลงานปฏิบัติการ'},
    'Set up the factory': {'th': 'ตั้งค่าโรงงาน'},
    'People, their accounts and units, and the product catalog.':
        {'th': 'พนักงาน บัญชีและหน่วยผลิตของพวกเขา และรายการผลิตภัณฑ์'},
    'Employees': {'th': 'พนักงาน'},
    'Products': {'th': 'ผลิตภัณฑ์'},
    'Processes': {'th': 'กระบวนการ'},
    'Select someone to expand their record. Changes save when you click Apply.':
        {'th': 'เลือกพนักงานเพื่อดูข้อมูล การเปลี่ยนแปลงจะบันทึกเมื่อกดบันทึก'},
    'Refresh list': {'th': 'โหลดรายการใหม่'},
    '+ Add employee': {'th': '+ เพิ่มพนักงาน'},
    'Add employee': {'th': 'เพิ่มพนักงาน'},
    'Employee added.': {'th': 'เพิ่มพนักงานแล้ว'},
    'First name *': {'th': 'ชื่อจริง *'},
    'Surname *': {'th': 'นามสกุล *'},
    'Enter both a first name and a surname.': {'th': 'กรุณากรอกทั้งชื่อจริงและนามสกุล'},
    'An email address is optional: the activation code is handed over in person.':
        {'th': 'อีเมลไม่บังคับ เพราะรหัสเปิดใช้งานจะส่งมอบให้โดยตรง'},
    'No employees match.': {'th': 'ไม่พบพนักงานที่ตรงกัน'},
    'No employees yet. Add the first one above.':
        {'th': 'ยังไม่มีพนักงาน เพิ่มคนแรกได้ด้านบน'},
    'Registered ': {'th': 'บันทึกเมื่อ '},
    ' · born ': {'th': ' · เกิด '},
    'This employee no longer exists. Refresh the list.':
        {'th': 'ไม่พบพนักงานคนนี้แล้ว กรุณาโหลดรายการใหม่'},

    'User account': {'th': 'บัญชีผู้ใช้'},
    'No account yet': {'th': 'ยังไม่มีบัญชี'},
    'Waiting for activation': {'th': 'รอการเปิดใช้งาน'},
    'Active': {'th': 'ใช้งานอยู่'},
    'Disabled': {'th': 'ปิดใช้งาน'},
    'Username ': {'th': 'ชื่อผู้ใช้ '},
    ' · code outstanding': {'th': ' · มีรหัสที่ยังใช้ได้'},
    ' · no code outstanding': {'th': ' · ไม่มีรหัสที่ใช้ได้'},
    'Username for a new account': {'th': 'ชื่อผู้ใช้สำหรับบัญชีใหม่'},
    'Only for an employee without an account': {'th': 'สำหรับพนักงานที่ยังไม่มีบัญชีเท่านั้น'},
    'Create account': {'th': 'สร้างบัญชี'},
    'Reissue code': {'th': 'ออกรหัสใหม่'},
    'Revoke code': {'th': 'ยกเลิกรหัส'},
    'Reset password': {'th': 'รีเซ็ตรหัสผ่าน'},
    'Disable account': {'th': 'ปิดใช้งานบัญชี'},
    'Enable account': {'th': 'เปิดใช้งานบัญชี'},
    'Resetting a password does not set one: the account returns to waiting for activation '
    'with a fresh code, and its owner chooses the password.':
        {'th': 'การรีเซ็ตไม่ได้ตั้งรหัสผ่านให้ บัญชีจะกลับไปสถานะรอการเปิดใช้งานพร้อมรหัสใหม่ '
               'และเจ้าของบัญชีเป็นผู้ตั้งรหัสผ่านเอง'},
    'This is your own account. Use your profile page.':
        {'th': 'นี่คือบัญชีของคุณเอง กรุณาใช้หน้าโปรไฟล์'},
    'Account created. Hand over the username and code; the code works once and expires in 7 days.':
        {'th': 'สร้างบัญชีแล้ว มอบชื่อผู้ใช้และรหัสให้เจ้าของบัญชี รหัสใช้ได้ครั้งเดียวและหมดอายุใน 7 วัน'},
    'A new code was issued. Any earlier code no longer works.':
        {'th': 'ออกรหัสใหม่แล้ว รหัสเดิมใช้ไม่ได้อีกต่อไป'},
    'There was no code left to revoke.': {'th': 'ไม่มีรหัสที่ต้องยกเลิก'},
    'The password was cleared and the account is waiting for activation again. '
    'Hand over this code.':
        {'th': 'ล้างรหัสผ่านแล้ว บัญชีกลับไปสถานะรอการเปิดใช้งาน กรุณามอบรหัสนี้ให้เจ้าของบัญชี'},
    'Account enabled.': {'th': 'เปิดใช้งานบัญชีแล้ว'},
    'Account disabled. Their sessions stop at the next request.':
        {'th': 'ปิดใช้งานบัญชีแล้ว เซสชันของผู้ใช้จะสิ้นสุดในคำขอถัดไป'},
    'Enter a username for the new account.': {'th': 'กรุณากรอกชื่อผู้ใช้สำหรับบัญชีใหม่'},
    'This employee already has an account.': {'th': 'พนักงานคนนี้มีบัญชีอยู่แล้ว'},
    'This employee has no account yet.': {'th': 'พนักงานคนนี้ยังไม่มีบัญชี'},
    'That username is already taken.': {'th': 'ชื่อผู้ใช้นี้ถูกใช้แล้ว'},
    'This account is already active. Reset its password instead.':
        {'th': 'บัญชีนี้ใช้งานอยู่แล้ว กรุณาใช้การรีเซ็ตรหัสผ่านแทน'},
    'You cannot administer your own account here. Use your profile page.':
        {'th': 'คุณไม่สามารถจัดการบัญชีของตนเองที่นี่ได้ กรุณาใช้หน้าโปรไฟล์'},
    'That account no longer exists. Refresh the list.':
        {'th': 'ไม่พบบัญชีนี้แล้ว กรุณาโหลดรายการใหม่'},

    'Website roles': {'th': 'บทบาทในระบบ'},
    'No website role': {'th': 'ยังไม่มีบทบาท'},
    'Save roles': {'th': 'บันทึกบทบาท'},
    'These decide which pages this person can open. The administrator role is set in the '
    'database, not here.':
        {'th': 'บทบาทกำหนดว่าผู้ใช้เปิดหน้าใดได้บ้าง บทบาทผู้ดูแลระบบกำหนดในฐานข้อมูล ไม่ใช่ที่นี่'},
    'No role changes to save.': {'th': 'ไม่มีการเปลี่ยนแปลงบทบาทให้บันทึก'},
    'Added ': {'th': 'เพิ่ม '},
    'Removed ': {'th': 'นำออก '},
    'You cannot change your own roles. Ask another administrator.':
        {'th': 'คุณไม่สามารถเปลี่ยนบทบาทของตนเองได้ กรุณาแจ้งผู้ดูแลระบบคนอื่น'},
    'The administrator role cannot be granted here':
        {'th': 'ไม่สามารถให้บทบาทผู้ดูแลระบบที่นี่ได้'},

    'Each production unit has at most one current supervisor. Unassign the present '
    'supervisor before assigning someone else; past assignments are kept.':
        {'th': 'แต่ละหน่วยผลิตมีหัวหน้างานปัจจุบันได้หนึ่งคน '
               'กรุณาปลดหัวหน้างานคนเดิมก่อนกำหนดคนใหม่ ประวัติการกำหนดจะถูกเก็บไว้'},
    'Refresh units': {'th': 'โหลดหน่วยผลิตใหม่'},
    'Assign': {'th': 'กำหนด'},
    'Unassign': {'th': 'ปลดออก'},
    'Select a supervisor': {'th': 'เลือกหัวหน้างาน'},
    'Select a supervisor before assigning.': {'th': 'กรุณาเลือกหัวหน้างานก่อนกำหนด'},
    'No supervisor assigned': {'th': 'ยังไม่มีหัวหน้างาน'},
    'Supervised by ': {'th': 'หัวหน้างาน: '},
    ' since ': {'th': ' ตั้งแต่ '},
    'Supervisor assigned.': {'th': 'กำหนดหัวหน้างานแล้ว'},
    'The unit now has no supervisor.': {'th': 'หน่วยผลิตนี้ไม่มีหัวหน้างานแล้ว'},
    'No production units exist yet. Ask an administrator to add them.':
        {'th': 'ยังไม่มีหน่วยผลิต กรุณาให้ผู้ดูแลระบบเพิ่มหน่วยผลิต'},
    'No employee holds the supervisor role, so units cannot be assigned yet.':
        {'th': 'ยังไม่มีพนักงานที่มีบทบาทหัวหน้างาน จึงยังกำหนดหน่วยผลิตไม่ได้'},
    'This production unit no longer exists. Refresh the list.':
        {'th': 'ไม่พบหน่วยผลิตนี้แล้ว กรุณาโหลดรายการใหม่'},
    'This unit already has a supervisor; end that assignment first':
        {'th': 'หน่วยผลิตนี้มีหัวหน้างานอยู่แล้ว กรุณาปลดคนเดิมก่อน'},
    'Employee must have the supervisor role': {'th': 'พนักงานต้องมีบทบาทหัวหน้างาน'},
    # ---------------------------------------------------- products and processes
    'A product needs a name. Its picture is uploaded here, stored in the database and '
    'shown on the Planner, Supervisor and Overview pages.':
        {'th': 'ผลิตภัณฑ์ต้องมีชื่อ รูปภาพอัปโหลดที่นี่ เก็บไว้ในฐานข้อมูล '
               'และแสดงในหน้าการวางแผน หัวหน้างาน และภาพรวม'},
    '+ Add product': {'th': '+ เพิ่มผลิตภัณฑ์'},
    'Create product': {'th': 'สร้างผลิตภัณฑ์'},
    'Reference code': {'th': 'รหัสอ้างอิง'},
    'No reference code': {'th': 'ไม่มีรหัสอ้างอิง'},
    'Description': {'th': 'คำอธิบาย'},
    'First process name *': {'th': 'ชื่อกระบวนการแรก *'},
    'Standard production': {'th': 'การผลิตมาตรฐาน'},
    'Drag a picture here or ': {'th': 'ลากรูปภาพมาวางที่นี่ หรือ '},
    'choose a file': {'th': 'เลือกไฟล์'},
    'Replace the picture: ': {'th': 'เปลี่ยนรูปภาพ: '},
    'PNG, JPEG or WebP. Large photos are shrunk and re-encoded before storage.':
        {'th': 'รองรับ PNG, JPEG หรือ WebP ภาพขนาดใหญ่จะถูกย่อและบีบอัดก่อนจัดเก็บ'},
    'Remove picture': {'th': 'ลบรูปภาพ'},
    'No picture': {'th': 'ไม่มีรูปภาพ'},
    'Picture updated.': {'th': 'อัปเดตรูปภาพแล้ว'},
    'Picture removed.': {'th': 'ลบรูปภาพแล้ว'},
    'Selected picture': {'th': 'รูปภาพที่เลือก'},
    ' Available to order': {'th': ' เปิดให้สั่งผลิต'},
    ' · Unavailable': {'th': ' · ไม่เปิดให้สั่ง'},
    'The product is created with an empty process. Add its steps on the Processes tab.':
        {'th': 'ผลิตภัณฑ์จะถูกสร้างพร้อมกระบวนการเปล่า เพิ่มขั้นตอนได้ที่แท็บกระบวนการ'},
    'Product created. Add its process steps on the Processes tab.':
        {'th': 'สร้างผลิตภัณฑ์แล้ว เพิ่มขั้นตอนการผลิตได้ที่แท็บกระบวนการ'},
    'Product created without its picture.': {'th': 'สร้างผลิตภัณฑ์แล้ว แต่ไม่ได้บันทึกรูปภาพ'},
    'Enter a product name.': {'th': 'กรุณากรอกชื่อผลิตภัณฑ์'},
    'Enter a product name and a name for its first process.':
        {'th': 'กรุณากรอกชื่อผลิตภัณฑ์และชื่อกระบวนการแรก'},
    'That product name or reference code is already used.':
        {'th': 'ชื่อผลิตภัณฑ์หรือรหัสอ้างอิงนี้ถูกใช้แล้ว'},
    'No products yet. Add the first one above.': {'th': 'ยังไม่มีผลิตภัณฑ์ เพิ่มรายการแรกได้ด้านบน'},
    'Upload an image file.': {'th': 'กรุณาอัปโหลดไฟล์รูปภาพ'},
    'That file is not a readable image. Use PNG, JPEG or WebP.':
        {'th': 'ไฟล์นี้ไม่ใช่รูปภาพที่อ่านได้ กรุณาใช้ PNG, JPEG หรือ WebP'},
    'That file could not be read. Upload a PNG, JPEG or WebP image.':
        {'th': 'ไม่สามารถอ่านไฟล์นี้ได้ กรุณาอัปโหลดรูปภาพ PNG, JPEG หรือ WebP'},
    'That file is empty.': {'th': 'ไฟล์นี้ว่างเปล่า'},
    'That image has too many pixels.': {'th': 'รูปภาพนี้มีความละเอียดสูงเกินไป'},

    'Production processes': {'th': 'กระบวนการผลิต'},
    'Applying an edit saves a new process version with its own step details. Existing '
    'work orders keep the route they were created with.':
        {'th': 'การบันทึกจะสร้างกระบวนการเวอร์ชันใหม่พร้อมรายละเอียดขั้นตอนของตัวเอง '
               'ใบสั่งผลิตที่มีอยู่จะยังใช้เส้นทางการผลิตเดิม'},
    'Process version': {'th': 'เวอร์ชันกระบวนการ'},
    'Process version *': {'th': 'เวอร์ชันกระบวนการ *'},
    'Select a process version': {'th': 'เลือกเวอร์ชันกระบวนการ'},
    'This product has no process yet': {'th': 'ผลิตภัณฑ์นี้ยังไม่มีกระบวนการ'},
    'Edit this process': {'th': 'แก้ไขกระบวนการนี้'},
    'Start a new process for this product': {'th': 'เริ่มกระบวนการใหม่สำหรับผลิตภัณฑ์นี้'},
    'Select the process version to edit.': {'th': 'เลือกเวอร์ชันกระบวนการที่ต้องการแก้ไข'},
    'That process belongs to another product. Refresh the list.':
        {'th': 'กระบวนการนี้เป็นของผลิตภัณฑ์อื่น กรุณาโหลดรายการใหม่'},
    'Editing ': {'th': 'กำลังแก้ไข '},
    'a new process': {'th': 'กระบวนการใหม่'},
    '. Nothing is saved until you click Apply.': {'th': '. ระบบจะยังไม่บันทึกจนกว่าคุณจะกดบันทึก'},
    'Process name *': {'th': 'ชื่อกระบวนการ *'},
    'Steps in order': {'th': 'ขั้นตอนตามลำดับ'},
    'No steps yet. A process may be saved empty.':
        {'th': 'ยังไม่มีขั้นตอน กระบวนการสามารถบันทึกโดยไม่มีขั้นตอนได้'},
    '+ Add a step': {'th': '+ เพิ่มขั้นตอน'},
    '+ Add an existing step': {'th': '+ เพิ่มขั้นตอนที่มีอยู่'},
    'Add selected step': {'th': 'เพิ่มขั้นตอนที่เลือก'},
    'Select a stored step': {'th': 'เลือกขั้นตอนที่บันทึกไว้'},
    'Select a stored step to add.': {'th': 'กรุณาเลือกขั้นตอนที่ต้องการเพิ่ม'},
    ' Make independent copy': {'th': ' ทำสำเนาแยกอิสระ'},
    'A copy lets you change this step without affecting the other processes that use it.':
        {'th': 'สำเนาช่วยให้แก้ไขขั้นตอนนี้ได้โดยไม่กระทบกระบวนการอื่นที่ใช้ขั้นตอนเดียวกัน'},
    'Shared step': {'th': 'ขั้นตอนที่ใช้ร่วมกัน'},
    'Unnamed step': {'th': 'ขั้นตอนที่ยังไม่มีชื่อ'},
    'Select a step to edit it, or add one.': {'th': 'เลือกขั้นตอนเพื่อแก้ไข หรือเพิ่มขั้นตอนใหม่'},
    'Step name *': {'th': 'ชื่อขั้นตอน *'},
    'Standard time (minutes)': {'th': 'เวลามาตรฐาน (นาที)'},
    'Describe the smaller operations of this step, one per line.':
        {'th': 'อธิบายงานย่อยของขั้นตอนนี้ บรรทัดละหนึ่งรายการ'},
    'Record operations such as tack welding inside their parent step rather than as '
    'separate steps.':
        {'th': 'ให้บันทึกงานย่อย เช่น การเชื่อมยึด ไว้ในขั้นตอนหลัก แทนการแยกเป็นขั้นตอนต่างหาก'},
    'Keep changes': {'th': 'เก็บการแก้ไข'},
    'Move earlier': {'th': 'เลื่อนขึ้น'},
    'Move later': {'th': 'เลื่อนลง'},
    'Removing a step removes it from this process only. Reordering never changes another '
    'process that uses the same step.':
        {'th': 'การนำขั้นตอนออกจะมีผลกับกระบวนการนี้เท่านั้น '
               'การจัดลำดับใหม่ไม่กระทบกระบวนการอื่นที่ใช้ขั้นตอนเดียวกัน'},
    'Draft discarded. Nothing was saved.': {'th': 'ยกเลิกฉบับร่างแล้ว ไม่มีการบันทึกข้อมูล'},
    'Process created.': {'th': 'สร้างกระบวนการแล้ว'},
    'Saved as version ': {'th': 'บันทึกเป็นเวอร์ชัน '},
    ' Earlier versions and existing orders are unchanged.':
        {'th': ' เวอร์ชันก่อนหน้าและใบสั่งผลิตที่มีอยู่ไม่เปลี่ยนแปลง'},
    'Enter a name for this process.': {'th': 'กรุณากรอกชื่อกระบวนการ'},
    ' needs a name.': {'th': ' ต้องมีชื่อ'},
    ' needs a production unit.': {'th': ' ต้องระบุหน่วยผลิต'},
    'That process reference code is already used.': {'th': 'รหัสอ้างอิงกระบวนการนี้ถูกใช้แล้ว'},
    'Production': {'th': 'การผลิต'},
    ' · Inactive': {'th': ' · ปิดใช้งาน'},
    'version ': {'th': 'เวอร์ชัน '},
    ' · v': {'th': ' · เวอร์ชัน'},
    'Product does not exist. Refresh the catalog.':
        {'th': 'ไม่พบผลิตภัณฑ์นี้ กรุณาโหลดรายการใหม่'},
    'Process does not exist. Refresh the catalog.':
        {'th': 'ไม่พบกระบวนการนี้ กรุณาโหลดรายการใหม่'},

    # ------------------------------------------------------- statistics (labels)
    'Production statistics': {'th': 'สถิติการผลิต'},
    'Filters': {'th': 'ตัวกรอง'},
    'Period': {'th': 'ช่วงเวลา'},
    'Completed between': {'th': 'เสร็จสิ้นระหว่าง'},
    'Timing summary': {'th': 'สรุปเวลา'},
    'Timing summaries': {'th': 'สรุปเวลา'},
    'Trends': {'th': 'แนวโน้ม'},
    'Bottlenecks': {'th': 'จุดคอขวด'},
    'Throughput': {'th': 'ปริมาณงานที่ผลิตได้'},
    'Throughput & lead time': {'th': 'ปริมาณงานและระยะเวลาผลิต'},
    'Data quality': {'th': 'คุณภาพข้อมูล'},
    'Records & export': {'th': 'บันทึกและการส่งออก'},
    'Export filtered records (CSV)': {'th': 'ส่งออกข้อมูลที่กรองไว้ (CSV)'},
    'Average': {'th': 'ค่าเฉลี่ย'},
    'Median': {'th': 'ค่ามัธยฐาน'},
    'Minutes': {'th': 'นาที'},
    ' min': {'th': ' นาที'},
    'Weekly': {'th': 'รายสัปดาห์'},
    'Monthly': {'th': 'รายเดือน'},
    'Overdue': {'th': 'เลยกำหนด'},
    'Overdue work orders': {'th': 'ใบสั่งผลิตที่เลยกำหนด'},
    'Completed work orders': {'th': 'ใบสั่งผลิตที่เสร็จสมบูรณ์'},
    'Days late': {'th': 'จำนวนวันที่ล่าช้า'},
    'No data loaded.': {'th': 'ยังไม่ได้โหลดข้อมูล'},
    'Statistics are unavailable. Adjust the filters or retry.':
        {'th': 'ไม่สามารถแสดงสถิติได้ กรุณาปรับตัวกรองหรือลองใหม่'},
    'No records match this selection.': {'th': 'ไม่มีข้อมูลที่ตรงกับการเลือกนี้'},
    'No completions in the selected period.': {'th': 'ไม่มีงานที่เสร็จในช่วงเวลาที่เลือก'},
    'All units': {'th': 'หน่วยผลิตทั้งหมด'},
    'All products': {'th': 'ผลิตภัณฑ์ทั้งหมด'},
    'All processes': {'th': 'กระบวนการทั้งหมด'},
    'All steps': {'th': 'ขั้นตอนทั้งหมด'},
    'All contractors': {'th': 'ผู้ว่าจ้างทั้งหมด'},
    'All work orders': {'th': 'ใบสั่งผลิตทั้งหมด'},
    'Could not log out. Check your connection and try again.':
        {'th': 'ออกจากระบบไม่สำเร็จ กรุณาตรวจสอบการเชื่อมต่อแล้วลองใหม่'},

    # ----------------------------------------------- account record and last administrator
    'History': {'th': 'ประวัติ'},
    'Show history': {'th': 'แสดงประวัติ'},
    'Nothing has been recorded for this person yet.':
        {'th': 'ยังไม่มีการบันทึกใดสำหรับบุคคลนี้'},
    'Role granted': {'th': 'ให้บทบาท'},
    'Role removed': {'th': 'นำบทบาทออก'},
    'Employee added': {'th': 'เพิ่มพนักงาน'},
    'Details edited': {'th': 'แก้ไขข้อมูล'},
    'Account created': {'th': 'สร้างบัญชี'},
    'Account edited': {'th': 'แก้ไขบัญชี'},
    'Activation code reissued': {'th': 'ออกรหัสเปิดใช้งานใหม่'},
    'Activation code revoked': {'th': 'ยกเลิกรหัสเปิดใช้งาน'},
    'Password reset': {'th': 'รีเซ็ตรหัสผ่าน'},
    'Account disabled': {'th': 'ปิดใช้งานบัญชี'},
    'Account enabled': {'th': 'เปิดใช้งานบัญชี'},
    'You cannot remove the only Operations Administrator. Please, assign the role to another '
    'employee to remove the role from this user.':
        {'th': 'คุณไม่สามารถนำผู้ดูแลงานปฏิบัติการคนเดียวออกได้ '
               'กรุณาให้บทบาทนี้แก่พนักงานคนอื่นก่อน จึงจะนำบทบาทออกจากผู้ใช้นี้ได้'},
    "You cannot disable or reset the only Operations Administrator's account. "
    'Please, assign the role to another employee first.':
        {'th': 'คุณไม่สามารถปิดใช้งานหรือรีเซ็ตบัญชีของผู้ดูแลงานปฏิบัติการคนเดียวได้ '
               'กรุณาให้บทบาทนี้แก่พนักงานคนอื่นก่อน'},

    # ------------------------------------------------------------------ orders page
    'Orders': {'th': 'ใบสั่งผลิต'},
    'Manage work orders': {'th': 'จัดการใบสั่งผลิต'},
    'Every work order in the factory. Select one to edit or cancel it.':
        {'th': 'ใบสั่งผลิตทั้งหมดในโรงงาน เลือกรายการเพื่อแก้ไขหรือยกเลิก'},
    'The work orders you created. Select one to edit or cancel it.':
        {'th': 'ใบสั่งผลิตที่คุณสร้าง เลือกรายการเพื่อแก้ไขหรือยกเลิก'},
    'No work orders match this search.': {'th': 'ไม่มีใบสั่งผลิตที่ตรงกับการค้นหานี้'},
    'Showing {first}–{last} of {total} orders': {'th': 'แสดง {first}–{last} จาก {total} ใบสั่งผลิต'},
    '{product} · {n} pieces · {contractor}': {'th': '{product} · {n} ชิ้น · {contractor}'},
    'Predicted finish: {eta}': {'th': 'คาดว่าจะเสร็จ: {eta}'},
    'No start date': {'th': 'ไม่มีวันเริ่ม'},
    'Cancelled': {'th': 'ยกเลิกแล้ว'},
    'Edit': {'th': 'แก้ไข'},
    'View': {'th': 'ดู'},
    'Notes': {'th': 'หมายเหตุ'},
    'Start date': {'th': 'วันเริ่ม'},
    'Due date': {'th': 'วันครบกำหนด'},
    'Cancel order': {'th': 'ยกเลิกใบสั่งผลิต'},
    'Yes, cancel this order': {'th': 'ใช่ ยกเลิกใบสั่งผลิตนี้'},
    'Cancelling removes this order from every queue and overview. It cannot be undone.':
        {'th': 'การยกเลิกจะนำใบสั่งผลิตนี้ออกจากทุกคิวงานและภาพรวม และไม่สามารถย้อนกลับได้'},
    'Work order cancelled.': {'th': 'ยกเลิกใบสั่งผลิตแล้ว'},
    'Select a contractor.': {'th': 'กรุณาเลือกผู้ว่าจ้าง'},
    'The product, process and quantity cannot change once pieces exist. To change them, cancel '
    'this order and create a new one.':
        {'th': 'เมื่อสร้างชิ้นงานแล้วจะเปลี่ยนผลิตภัณฑ์ กระบวนการ และจำนวนไม่ได้ '
               'หากต้องการเปลี่ยน กรุณายกเลิกใบสั่งผลิตนี้แล้วสร้างใหม่'},
    'Complete and cancelled orders can no longer be changed.':
        {'th': 'ใบสั่งผลิตที่เสร็จสมบูรณ์หรือยกเลิกแล้วไม่สามารถแก้ไขได้'},
    'This work order number already exists. Use a different number. Nothing was saved.':
        {'th': 'เลขที่ใบสั่งผลิตนี้มีอยู่แล้ว กรุณาใช้เลขอื่น ไม่มีการบันทึกใด ๆ'},
    'Due date cannot precede start date': {'th': 'วันครบกำหนดต้องไม่ก่อนวันเริ่ม'},
    'Selected contractor does not exist': {'th': 'ไม่พบผู้ว่าจ้างที่เลือก'},
    'This work order does not exist or is not yours to manage.':
        {'th': 'ไม่พบใบสั่งผลิตนี้ หรือคุณไม่มีสิทธิ์จัดการ'},
    'This work order was cancelled and can no longer be changed.':
        {'th': 'ใบสั่งผลิตนี้ถูกยกเลิกแล้วและไม่สามารถแก้ไขได้'},
    'This work order is complete and can no longer be changed.':
        {'th': 'ใบสั่งผลิตนี้เสร็จสมบูรณ์แล้วและไม่สามารถแก้ไขได้'},
    'No order changes supplied': {'th': 'ไม่มีการเปลี่ยนแปลงใบสั่งผลิต'},

    # ------------------------------------------------------ overview for supervisors
    'Supervisor console': {'th': 'แผงควบคุมหัวหน้างาน'},
    'Only work orders with a step in a unit you supervise are shown, and the counts cover '
    'those orders only.':
        {'th': 'แสดงเฉพาะใบสั่งผลิตที่มีขั้นตอนในหน่วยผลิตที่คุณดูแล และตัวเลขสรุปนับเฉพาะใบสั่งผลิตเหล่านั้น'},

    # ------------------------------------------------------------- completion dialog
    'Quantity (pieces)': {'th': 'จำนวน (ชิ้น)'},
    'Quick quantities': {'th': 'จำนวนด่วน'},
    'Progress of the current step': {'th': 'ความคืบหน้าของขั้นตอนปัจจุบัน'},
    'Pieces finished at this step': {'th': 'ชิ้นงานที่ผ่านขั้นตอนนี้แล้ว'},
    'Set quantity to {n}': {'th': 'ตั้งจำนวนเป็น {n}'},
    'All ({n})': {'th': 'ทั้งหมด ({n})'},
    '{order} · {step} · {count} eligible of {total} pieces':
        {'th': '{order} · {step} · ทำได้ {count} จาก {total} ชิ้น'},
    '{q} pieces started.': {'th': 'เริ่มงาน {q} ชิ้นแล้ว'},
    '{q} pieces completed.': {'th': 'ทำเสร็จ {q} ชิ้นแล้ว'},
    '{q} pieces marked already prepared.': {'th': 'บันทึก {q} ชิ้นว่าเตรียมไว้แล้ว'},
    '{running} running, {ready} ready to start.':
        {'th': 'กำลังทำ {running} ชิ้น พร้อมเริ่ม {ready} ชิ้น'},
    '{left} of {total} pieces still to finish at this step.':
        {'th': 'เหลืออีก {left} จาก {total} ชิ้นที่ต้องทำให้เสร็จในขั้นตอนนี้'},
    'Every piece has finished this step.': {'th': 'ทุกชิ้นผ่านขั้นตอนนี้แล้ว'},
    'Due date · nearest first': {'th': 'วันครบกำหนด · ใกล้ที่สุดก่อน'},
    'Due date · latest first': {'th': 'วันครบกำหนด · ช้าที่สุดก่อน'},
    'Created · newest first': {'th': 'วันที่สร้าง · ใหม่ที่สุดก่อน'},
    'Created · oldest first': {'th': 'วันที่สร้าง · เก่าที่สุดก่อน'},
    'Read': {'th': 'อ่านแล้ว'},
    'Language': {'th': 'ภาษา'},

    # ------------------------------------------ statistics (labels, notes and charts)
    'Duration distribution': {'th': 'การกระจายของระยะเวลา'},
    'Current work at risk': {'th': 'งานปัจจุบันที่มีความเสี่ยง'},
    'Mean': {'th': 'ค่าเฉลี่ย'},
    'Executions': {'th': 'จำนวนการปฏิบัติงาน'},
    'Standard deviation': {'th': 'ส่วนเบี่ยงเบนมาตรฐาน'},
    'Duration': {'th': 'ระยะเวลา'},
    'Sample': {'th': 'จำนวนตัวอย่าง'},
    '90th percentile': {'th': 'เปอร์เซ็นไทล์ที่ 90'},
    'Excluded': {'th': 'ที่ตัดออก'},
    'Raw': {'th': 'ข้อมูลดิบ'},
    'Adjusted': {'th': 'ปรับแล้ว'},
    'Basis': {'th': 'ฐานการคำนวณ'},
    'Adjusted (outliers excluded)': {'th': 'ปรับแล้ว (ตัดค่าผิดปกติออก)'},
    'Raw (all executions)': {'th': 'ข้อมูลดิบ (ทุกการปฏิบัติงาน)'},
    'Trend grain': {'th': 'ช่วงของแนวโน้ม'},
    'Orders I created': {'th': 'ใบสั่งผลิตที่ฉันสร้าง'},
    'Select a step': {'th': 'เลือกขั้นตอน'},
    'Saved filter combinations': {'th': 'ชุดตัวกรองที่บันทึกไว้'},
    'Name this combination': {'th': 'ตั้งชื่อชุดตัวกรองนี้'},
    'Name the combination before saving it.': {'th': 'กรุณาตั้งชื่อชุดตัวกรองก่อนบันทึก'},
    'Load statistics before saving these filters.': {'th': 'กรุณาโหลดสถิติก่อนบันทึกตัวกรองเหล่านี้'},
    'Select a saved combination to delete.': {'th': 'เลือกชุดตัวกรองที่บันทึกไว้เพื่อลบ'},
    'Travel time': {'th': 'เวลาขนย้าย'},
    'Process time': {'th': 'เวลาดำเนินการ'},
    'Combined duration': {'th': 'ระยะเวลารวม'},
    'Minor': {'th': 'เล็กน้อย'},
    'Moderate': {'th': 'ปานกลาง'},
    'Major': {'th': 'มาก'},
    'Severe': {'th': 'รุนแรง'},
    'Position': {'th': 'ลำดับ'},
    'Piece': {'th': 'ชิ้นงาน'},
    'Previous step finished': {'th': 'ขั้นตอนก่อนหน้าเสร็จเมื่อ'},
    'Started': {'th': 'เริ่มเมื่อ'},
    'Travel (min)': {'th': 'ขนย้าย (นาที)'},
    'Process (min)': {'th': 'ดำเนินการ (นาที)'},
    'Combined (min)': {'th': 'รวม (นาที)'},
    'Standard (min)': {'th': 'มาตรฐาน (นาที)'},
    'Excess (min)': {'th': 'ส่วนเกิน (นาที)'},
    'Over standard (%)': {'th': 'เกินมาตรฐาน (%)'},
    'Severity': {'th': 'ระดับความรุนแรง'},
    'Outlier': {'th': 'ค่าผิดปกติ'},
    'Outlier metrics': {'th': 'ตัววัดที่ผิดปกติ'},
    'No': {'th': 'ไม่ใช่'},
    'Completed piece-step executions': {'th': 'การปฏิบัติงานต่อชิ้นต่อขั้นตอนที่เสร็จแล้ว'},
    'Timing observations in the selected period': {'th': 'ข้อมูลเวลาในช่วงที่เลือก'},
    'Travel · median': {'th': 'ขนย้าย · ค่ามัธยฐาน'},
    'Process · median': {'th': 'ดำเนินการ · ค่ามัธยฐาน'},
    'Combined · median': {'th': 'รวม · ค่ามัธยฐาน'},
    '{n} adjusted observations': {'th': 'ข้อมูลที่ปรับแล้ว {n} รายการ'},
    'Each figure counts one completed piece-step execution, because standard times are defined '
    'per piece. Whole-order elapsed durations are reported separately under Throughput & lead time.':
        {'th': 'ตัวเลขแต่ละค่านับหนึ่งการปฏิบัติงานต่อชิ้นต่อขั้นตอนที่เสร็จแล้ว เพราะเวลามาตรฐานกำหนดต่อชิ้น '
               'ระยะเวลาของทั้งใบสั่งผลิตแสดงแยกไว้ในหัวข้อ ปริมาณงานและระยะเวลาผลิต'},
    'Tukey upper fence: Q3 + {multiplier} x IQR, computed for each process version and step with '
    'at least {minimum} observations. Excluded executions are kept and can be inspected.':
        {'th': 'ขอบบนของ Tukey: Q3 + {multiplier} x IQR คำนวณแยกตามเวอร์ชันกระบวนการและขั้นตอนที่มีข้อมูล'
               'อย่างน้อย {minimum} รายการ การปฏิบัติงานที่ถูกตัดออกยังคงเก็บไว้และตรวจดูได้'},
    'Inspect excluded outliers': {'th': 'ตรวจดูค่าผิดปกติที่ตัดออก'},
    '{n} executions have no recorded previous-step timestamp, so their travel time is unknown '
    'rather than zero.':
        {'th': 'การปฏิบัติงาน {n} รายการไม่มีเวลาของขั้นตอนก่อนหน้า จึงไม่ทราบเวลาขนย้าย (ไม่ใช่ศูนย์)'},
    '{n} executions have no configured standard time and are reported as Not assessable.':
        {'th': 'การปฏิบัติงาน {n} รายการไม่มีเวลามาตรฐานที่ตั้งไว้ จึงแสดงเป็น ประเมินไม่ได้'},
    '{n} pieces were marked Already prepared. They are finished requirements with no processing, '
    'never zero-duration work.':
        {'th': 'ชิ้นงาน {n} ชิ้นถูกบันทึกว่าเตรียมไว้แล้ว ถือว่าผ่านขั้นตอนโดยไม่มีการดำเนินการ '
               'ไม่ใช่งานที่ใช้เวลาเป็นศูนย์'},
    '{n} executions across {orders} cancelled work orders are excluded from every figure on this page.':
        {'th': 'การปฏิบัติงาน {n} รายการจากใบสั่งผลิตที่ยกเลิก {orders} ใบ ไม่ถูกนับในทุกตัวเลขของหน้านี้'},
    'Select a process step with completed executions.': {'th': 'เลือกขั้นตอนที่มีการปฏิบัติงานเสร็จแล้ว'},
    'Bars are one standard deviation wide.': {'th': 'แท่งแต่ละแท่งกว้างหนึ่งส่วนเบี่ยงเบนมาตรฐาน'},
    'Bars widened to {n} standard deviations so the full range stays readable.':
        {'th': 'ขยายความกว้างแท่งเป็น {n} ส่วนเบี่ยงเบนมาตรฐานเพื่อให้อ่านช่วงข้อมูลทั้งหมดได้'},
    'No completed executions match these filters.': {'th': 'ไม่มีการปฏิบัติงานที่เสร็จแล้วตรงกับตัวกรองนี้'},
    'Only one execution: a distribution needs more observations.':
        {'th': 'มีการปฏิบัติงานเพียงรายการเดียว ต้องมีข้อมูลมากกว่านี้จึงจะแสดงการกระจายได้'},
    'Every execution took the same time, so the distribution has no width.':
        {'th': 'ทุกการปฏิบัติงานใช้เวลาเท่ากัน การกระจายจึงไม่มีความกว้าง'},
    'These durations are noticeably skewed, so the fitted normal curve is only a rough reference.':
        {'th': 'ระยะเวลาเหล่านี้เบ้อย่างชัดเจน เส้นโค้งปกติที่ประมาณไว้จึงใช้อ้างอิงคร่าว ๆ เท่านั้น'},
    'The standard process time is not drawn here: it applies to process time only, never to '
    'travel or combined duration.':
        {'th': 'ไม่แสดงเวลามาตรฐานที่นี่ เพราะใช้กับเวลาดำเนินการเท่านั้น ไม่ใช้กับเวลาขนย้ายหรือระยะเวลารวม'},
    'No single standard process time applies to this selection.':
        {'th': 'การเลือกนี้ไม่มีเวลามาตรฐานเดียวที่ใช้ร่วมกัน'},
    'Fitted normal curve': {'th': 'เส้นโค้งการแจกแจงปกติที่ประมาณไว้'},
    '{label} (minutes)': {'th': '{label} (นาที)'},
    '%{customdata[0]:.1f}–%{customdata[1]:.1f} min<br>%{y} executions (%{customdata[2]:.1f}%)<extra></extra>':
        {'th': '%{customdata[0]:.1f}–%{customdata[1]:.1f} นาที<br>%{y} การปฏิบัติงาน (%{customdata[2]:.1f}%)<extra></extra>'},
    '%{x:.1f} min average<br>%{customdata[0]} observations<extra></extra>':
        {'th': 'เฉลี่ย %{x:.1f} นาที<br>%{customdata[0]} รายการ<extra></extra>'},
    '%{y:.1f} min<br>%{customdata[0]} observations<extra></extra>':
        {'th': '%{y:.1f} นาที<br>%{customdata[0]} รายการ<extra></extra>'},
    'Average minutes per piece': {'th': 'นาทีเฉลี่ยต่อชิ้น'},
    'Period start': {'th': 'เริ่มช่วงเวลา'},
    'Step completions': {'th': 'จำนวนที่ผ่านขั้นตอน'},
    'Executions over standard': {'th': 'การปฏิบัติงานที่เกินมาตรฐาน'},
    'Share of assessable executions': {'th': 'สัดส่วนของการปฏิบัติงานที่ประเมินได้'},
    '{n} assessable of {total}': {'th': 'ประเมินได้ {n} จาก {total}'},
    'Affected work orders': {'th': 'ใบสั่งผลิตที่ได้รับผลกระทบ'},
    'Distinct orders': {'th': 'นับใบสั่งผลิตไม่ซ้ำ'},
    'Average excess': {'th': 'ส่วนเกินเฉลี่ย'},
    'Average {percent} over standard': {'th': 'เกินมาตรฐานเฉลี่ย {percent}'},
    'Not assessable': {'th': 'ประเมินไม่ได้'},
    'No configured standard time': {'th': 'ไม่มีเวลามาตรฐานที่ตั้งไว้'},
    'Severity bands': {'th': 'ระดับความรุนแรง'},
    'Band': {'th': 'ระดับ'},
    'Bands measure how far process time exceeded the standard: Minor up to 10%, Moderate up to '
    '25%, Major up to 50%, Severe above 50%.':
        {'th': 'ระดับวัดว่าเวลาดำเนินการเกินมาตรฐานมากเพียงใด: เล็กน้อย ไม่เกิน 10% ปานกลาง ไม่เกิน 25% '
               'มาก ไม่เกิน 50% รุนแรง เกิน 50%'},
    'Process time is compared with the standard process time only. Travel and combined duration '
    'are never judged against it.':
        {'th': 'เวลาดำเนินการเปรียบเทียบกับเวลามาตรฐานเท่านั้น เวลาขนย้ายและระยะเวลารวมไม่ถูกเทียบกับมาตรฐาน'},
    'No historical standard is stored with each execution, so past work is compared with the '
    'standard configured today. Treat these historical comparisons as current-standard comparisons '
    'rather than the value in force at the time.':
        {'th': 'ระบบไม่ได้เก็บเวลามาตรฐานในอดีตไว้กับแต่ละการปฏิบัติงาน งานในอดีตจึงเทียบกับมาตรฐานที่ตั้งไว้ในปัจจุบัน '
               'ให้ถือว่าเป็นการเทียบกับมาตรฐานปัจจุบัน ไม่ใช่ค่าที่ใช้อยู่ในขณะนั้น'},
    'Genuine long executions stay in these counts even when the adjusted timing summaries exclude '
    'them as outliers.':
        {'th': 'การปฏิบัติงานที่ใช้เวลานานจริงยังคงถูกนับที่นี่ แม้สรุปเวลาแบบปรับแล้วจะตัดออกเป็นค่าผิดปกติ'},
    'Step comparison': {'th': 'เปรียบเทียบขั้นตอน'},
    'Steps are grouped by product and process version, so incomparable routes are never averaged '
    'together. Select a bar to inspect its records, or use the Records & export tab.':
        {'th': 'ขั้นตอนจัดกลุ่มตามผลิตภัณฑ์และเวอร์ชันกระบวนการ จึงไม่นำเส้นทางที่เทียบกันไม่ได้มาเฉลี่ยรวมกัน '
               'เลือกแท่งเพื่อตรวจดูข้อมูล หรือใช้แท็บ บันทึกและการส่งออก'},
    'Product · process version': {'th': 'ผลิตภัณฑ์ · เวอร์ชันกระบวนการ'},
    'Travel average': {'th': 'เวลาขนย้ายเฉลี่ย'},
    'Process average': {'th': 'เวลาดำเนินการเฉลี่ย'},
    'Combined average': {'th': 'ระยะเวลารวมเฉลี่ย'},
    'Ready-to-start quantity is live work waiting at each step, not a historical figure.':
        {'th': 'จำนวนที่พร้อมเริ่มคืองานที่รออยู่ในแต่ละขั้นตอนขณะนี้ ไม่ใช่ตัวเลขในอดีต'},
    'Compared with the preceding equivalent period': {'th': 'เปรียบเทียบกับช่วงเวลาก่อนหน้าที่ยาวเท่ากัน'},
    'Preceding period: {start} to {end} · {n} completed executions':
        {'th': 'ช่วงก่อนหน้า: {start} ถึง {end} · การปฏิบัติงานที่เสร็จ {n} รายการ'},
    'Measure': {'th': 'ตัววัด'},
    'Selected period': {'th': 'ช่วงที่เลือก'},
    'Preceding period': {'th': 'ช่วงก่อนหน้า'},
    '{measure} average': {'th': '{measure} เฉลี่ย'},
    'No completed executions in the selected period.': {'th': 'ไม่มีการปฏิบัติงานที่เสร็จในช่วงที่เลือก'},
    'Weekly timing and over-standard trend': {'th': 'แนวโน้มเวลาและการเกินมาตรฐานรายสัปดาห์'},
    'Monthly timing and over-standard trend': {'th': 'แนวโน้มเวลาและการเกินมาตรฐานรายเดือน'},
    'Completions': {'th': 'จำนวนที่เสร็จ'},
    'Completed in the period': {'th': 'เสร็จในช่วงเวลานี้'},
    'Creation to completion': {'th': 'ตั้งแต่สร้างจนเสร็จ'},
    'Production start to completion': {'th': 'ตั้งแต่เริ่มผลิตจนเสร็จ'},
    'Median of {n} orders': {'th': 'ค่ามัธยฐานจาก {n} ใบสั่งผลิต'},
    'Delivered by due date': {'th': 'ส่งมอบทันวันครบกำหนด'},
    '{n} of {total} dated orders': {'th': '{n} จาก {total} ใบสั่งผลิตที่มีวันครบกำหนด'},
    'Due-date delivery measures whole orders against their planned due date. It is a different '
    'measure from step-standard overruns, which compare per-piece process time with a step standard.':
        {'th': 'การส่งมอบตามวันครบกำหนดวัดทั้งใบสั่งผลิตเทียบกับวันครบกำหนดที่วางแผนไว้ '
               'ซึ่งต่างจากการเกินมาตรฐานของขั้นตอนที่เทียบเวลาดำเนินการต่อชิ้นกับมาตรฐานของขั้นตอน'},
    '{n} completed orders have no recorded production start, so their production lead time is '
    'unknown rather than zero.':
        {'th': 'ใบสั่งผลิตที่เสร็จแล้ว {n} ใบไม่มีเวลาเริ่มผลิต จึงไม่ทราบระยะเวลาผลิต (ไม่ใช่ศูนย์)'},
    'Step completions count each piece once per step it finishes; finished pieces count each piece '
    'once, when its last route step completes.':
        {'th': 'จำนวนที่ผ่านขั้นตอนนับชิ้นงานหนึ่งครั้งต่อทุกขั้นตอนที่ทำเสร็จ '
               'ชิ้นงานที่เสร็จนับชิ้นงานหนึ่งครั้งเมื่อขั้นตอนสุดท้ายเสร็จ'},
    'Per step': {'th': 'ต่อขั้นตอน'},
    'Running beyond standard': {'th': 'กำลังทำเกินเวลามาตรฐาน'},
    'Pieces in process now': {'th': 'ชิ้นงานที่กำลังทำอยู่'},
    'Ready and waiting': {'th': 'พร้อมและรออยู่'},
    'Pieces with travel time running': {'th': 'ชิ้นงานที่อยู่ระหว่างขนย้าย'},
    'Past their due date': {'th': 'เลยวันครบกำหนดแล้ว'},
    'This section shows live work as of the moment the page loaded. It is not limited by the '
    'completed-between date filter, because none of these pieces has finished; the product, '
    'process, step, unit, contractor and work-order filters do apply.':
        {'th': 'ส่วนนี้แสดงงานปัจจุบัน ณ เวลาที่โหลดหน้า ไม่จำกัดด้วยตัวกรองช่วงวันที่เสร็จ '
               'เพราะชิ้นงานเหล่านี้ยังไม่เสร็จ แต่ตัวกรองผลิตภัณฑ์ กระบวนการ ขั้นตอน หน่วยผลิต '
               'ผู้ว่าจ้าง และใบสั่งผลิตยังคงมีผล'},
    'Running pieces beyond standard process time': {'th': 'ชิ้นงานที่กำลังทำเกินเวลามาตรฐาน'},
    'No running piece currently exceeds its standard process time.':
        {'th': 'ขณะนี้ไม่มีชิ้นงานที่กำลังทำเกินเวลามาตรฐาน'},
    'Ready pieces with the longest ongoing travel time': {'th': 'ชิ้นงานพร้อมเริ่มที่รอขนย้ายนานที่สุด'},
    'No ready piece is waiting to start.': {'th': 'ไม่มีชิ้นงานพร้อมเริ่มที่รออยู่'},
    'First route steps have no travel time and are not listed here.':
        {'th': 'ขั้นตอนแรกของเส้นทางไม่มีเวลาขนย้ายและไม่แสดงที่นี่'},
    'Work orders past their due date': {'th': 'ใบสั่งผลิตที่เลยวันครบกำหนด'},
    'No outstanding work order is past its due date.': {'th': 'ไม่มีใบสั่งผลิตค้างที่เลยวันครบกำหนด'},
    'Waiting since': {'th': 'รอตั้งแต่'},
    'Travel so far': {'th': 'เวลาขนย้ายจนถึงตอนนี้'},
    'Steps finished': {'th': 'ขั้นตอนที่เสร็จ'},
    'Contributing records': {'th': 'ข้อมูลที่เกี่ยวข้อง'},
    'Every record keeps its order, product, process version, step, unit, timestamps, durations, '
    'standard, excess and outlier status. Excluded outliers are shown, never deleted.':
        {'th': 'ทุกรายการเก็บใบสั่งผลิต ผลิตภัณฑ์ เวอร์ชันกระบวนการ ขั้นตอน หน่วยผลิต เวลา ระยะเวลา '
               'มาตรฐาน ส่วนเกิน และสถานะค่าผิดปกติ ค่าผิดปกติที่ตัดออกยังแสดงอยู่ ไม่ถูกลบ'},
    'Clear selection': {'th': 'ล้างการเลือก'},
    'Exports apply the same access scope, filters and calculation rules as this page.':
        {'th': 'การส่งออกใช้ขอบเขตสิทธิ์ ตัวกรอง และกฎการคำนวณเดียวกับหน้านี้'},
    'Selected records': {'th': 'ข้อมูลที่เลือก'},
    'Executions excluded as upper outliers': {'th': 'การปฏิบัติงานที่ถูกตัดออกเป็นค่าผิดปกติด้านบน'},
    'Executions over the standard process time': {'th': 'การปฏิบัติงานที่เกินเวลามาตรฐาน'},

    # ------------------------------------------------ floor confirmation, scrap and pauses
    'This action is irreversible. Only a manager can correct a mistaken entry.':
        {'th': 'การดำเนินการนี้ย้อนกลับไม่ได้ มีเพียงผู้จัดการเท่านั้นที่แก้ไขรายการที่ผิดพลาดได้'},
    'You are about to start {q} pieces of {order} · {step}.':
        {'th': 'คุณกำลังจะเริ่มงาน {q} ชิ้นของ {order} · {step}'},
    'You are about to complete {q} pieces of {order} · {step}.':
        {'th': 'คุณกำลังจะบันทึกว่าทำเสร็จ {q} ชิ้นของ {order} · {step}'},
    'You are about to mark {q} pieces of {order} · {step} as already prepared.':
        {'th': 'คุณกำลังจะบันทึก {q} ชิ้นของ {order} · {step} ว่าเตรียมไว้แล้ว'},
    'You are about to scrap {q} pieces of {order} · {step}. They will not continue to the next step.':
        {'th': 'คุณกำลังจะบันทึกของเสีย {q} ชิ้นของ {order} · {step} ชิ้นงานเหล่านี้จะไม่ไปขั้นตอนถัดไป'},
    'Yes, record {q} pieces': {'th': 'ใช่ บันทึก {q} ชิ้น'},
    'Enter a whole number from 1 to {n}.': {'th': 'กรุณากรอกจำนวนเต็มตั้งแต่ 1 ถึง {n}'},
    'Scrap pieces': {'th': 'บันทึกของเสีย'},
    '{q} pieces scrapped.': {'th': 'บันทึกของเสีย {q} ชิ้นแล้ว'},
    '{n} scrapped': {'th': 'ของเสีย {n} ชิ้น'},
    'What should happen next?': {'th': 'ควรทำอะไรต่อ'},
    'Make replacement pieces': {'th': 'ผลิตชิ้นงานทดแทน'},
    'Review with a manager': {'th': 'ให้ผู้จัดการตรวจสอบ'},
    'No action needed': {'th': 'ไม่ต้องดำเนินการ'},
    'What happened? (optional)': {'th': 'เกิดอะไรขึ้น (ไม่บังคับ)'},
    'Replacement pieces were requested.': {'th': 'ขอชิ้นงานทดแทนแล้ว'},
    'A review was requested.': {'th': 'ขอให้ตรวจสอบแล้ว'},
    'Choose Start, Complete, Already prepared or Scrap':
        {'th': 'กรุณาเลือก เริ่ม เสร็จ เตรียมไว้แล้ว หรือ ของเสีย'},
    'Choose what should happen to the scrapped pieces': {'th': 'กรุณาเลือกว่าจะทำอย่างไรกับของเสีย'},
    'Break': {'th': 'พัก'},
    'Machine breakdown': {'th': 'เครื่องจักรเสีย'},
    'Waiting for material': {'th': 'รอวัตถุดิบ'},
    'Quality check': {'th': 'ตรวจสอบคุณภาพ'},
    'Other': {'th': 'อื่น ๆ'},
    'Pause step': {'th': 'หยุดขั้นตอนชั่วคราว'},
    'Resume step': {'th': 'ทำขั้นตอนต่อ'},
    'Paused: {reason}': {'th': 'หยุดชั่วคราว: {reason}'},
    ' since {time} by {name}': {'th': ' ตั้งแต่ {time} โดย {name}'},
    'Paused time is recorded and shown in Statistics. Due dates do not move.':
        {'th': 'เวลาที่หยุดจะถูกบันทึกและแสดงในสถิติ วันครบกำหนดไม่เปลี่ยน'},
    'Step paused. Resume it as soon as work continues.':
        {'th': 'หยุดขั้นตอนชั่วคราวแล้ว กรุณากดทำต่อทันทีที่เริ่มงานอีกครั้ง'},
    'Step resumed.': {'th': 'ทำขั้นตอนต่อแล้ว'},
    'This step is paused. Resume it before starting or completing pieces.':
        {'th': 'ขั้นตอนนี้หยุดอยู่ กรุณากดทำต่อก่อนเริ่มหรือบันทึกงานเสร็จ'},
    'Choose why the step is paused': {'th': 'กรุณาเลือกเหตุผลที่หยุด'},
    'Only a step with pieces in progress can be paused.':
        {'th': 'หยุดได้เฉพาะขั้นตอนที่มีชิ้นงานกำลังทำอยู่'},
    'This step is already paused.': {'th': 'ขั้นตอนนี้หยุดอยู่แล้ว'},
    'This step is not paused.': {'th': 'ขั้นตอนนี้ไม่ได้หยุดอยู่'},

    # --------------------------------------------------------- corrections and requests
    'Recorded floor actions': {'th': 'รายการที่บันทึกจากหน้างาน'},
    'Reversing undoes exactly the pieces that action changed, and is refused when later work '
    'depends on them. The reason is kept.':
        {'th': 'การย้อนกลับจะยกเลิกเฉพาะชิ้นงานที่รายการนั้นเปลี่ยน และทำไม่ได้หากมีงานต่อเนื่องแล้ว เหตุผลจะถูกเก็บไว้'},
    'When': {'th': 'เมื่อ'},
    'Action': {'th': 'การดำเนินการ'},
    'Correction': {'th': 'การแก้ไข'},
    'Scrapped': {'th': 'ของเสีย'},
    'Reverse': {'th': 'ย้อนกลับ'},
    'Reason for reversing': {'th': 'เหตุผลที่ย้อนกลับ'},
    'Reversed by {name}: {reason}': {'th': 'ย้อนกลับโดย {name}: {reason}'},
    'Recorded before corrections were possible': {'th': 'บันทึกก่อนมีระบบแก้ไข'},
    'No floor actions have been recorded for this order yet.':
        {'th': 'ยังไม่มีการบันทึกจากหน้างานสำหรับใบสั่งผลิตนี้'},
    'Give a reason before reversing an action.': {'th': 'กรุณาระบุเหตุผลก่อนย้อนกลับ'},
    'Reversed: {n} pieces are back as they were before this action.':
        {'th': 'ย้อนกลับแล้ว: ชิ้นงาน {n} ชิ้นกลับสู่สถานะก่อนรายการนี้'},
    'This action no longer exists.': {'th': 'ไม่พบรายการนี้แล้ว'},
    'This work order was cancelled; its actions can no longer change.':
        {'th': 'ใบสั่งผลิตนี้ถูกยกเลิกแล้ว จึงเปลี่ยนรายการไม่ได้'},
    'This action was already reversed.': {'th': 'รายการนี้ถูกย้อนกลับแล้ว'},
    'This action was recorded before corrections were possible, so it cannot be reversed here.':
        {'th': 'รายการนี้บันทึกก่อนมีระบบแก้ไข จึงย้อนกลับที่นี่ไม่ได้'},
    'Some of these pieces were completed or scrapped since. Reverse those actions first.':
        {'th': 'ชิ้นงานบางชิ้นถูกบันทึกเสร็จหรือเป็นของเสียแล้ว กรุณาย้อนกลับรายการเหล่านั้นก่อน'},
    'Some of these pieces have moved on to a later step or were scrapped. Reverse those actions first.':
        {'th': 'ชิ้นงานบางชิ้นไปขั้นตอนถัดไปหรือเป็นของเสียแล้ว กรุณาย้อนกลับรายการเหล่านั้นก่อน'},
    'These pieces are no longer scrapped at this step.': {'th': 'ชิ้นงานเหล่านี้ไม่ได้เป็นของเสียในขั้นตอนนี้แล้ว'},
    'Replacement pieces were already added for this scrap, so it cannot be reversed.':
        {'th': 'มีการเพิ่มชิ้นงานทดแทนสำหรับของเสียนี้แล้ว จึงย้อนกลับไม่ได้'},
    'Invalid action identifier': {'th': 'รหัสรายการไม่ถูกต้อง'},
    'Action requested ({n})': {'th': 'มีคำขอดำเนินการ ({n})'},
    'Scrapped pieces: action requested': {'th': 'ของเสีย: มีคำขอดำเนินการ'},
    '{n} pieces scrapped at {step}': {'th': 'ของเสีย {n} ชิ้นที่ {step}'},
    'Replacement pieces requested': {'th': 'ขอชิ้นงานทดแทน'},
    'Review requested': {'th': 'ขอให้ตรวจสอบ'},
    'Replacement pieces': {'th': 'ชิ้นงานทดแทน'},
    'Note (optional)': {'th': 'หมายเหตุ (ไม่บังคับ)'},
    'Add replacement pieces': {'th': 'เพิ่มชิ้นงานทดแทน'},
    'Close without replacements': {'th': 'ปิดโดยไม่ผลิตทดแทน'},
    'Enter how many replacement pieces to make.': {'th': 'กรุณากรอกจำนวนชิ้นงานทดแทน'},
    'Enter how many replacement pieces to make': {'th': 'กรุณากรอกจำนวนชิ้นงานทดแทน'},
    '{n} replacement pieces added. They start at the first step.':
        {'th': 'เพิ่มชิ้นงานทดแทน {n} ชิ้นแล้ว เริ่มที่ขั้นตอนแรก'},
    'Request closed.': {'th': 'ปิดคำขอแล้ว'},
    'Choose to add replacement pieces or close the request':
        {'th': 'กรุณาเลือกเพิ่มชิ้นงานทดแทนหรือปิดคำขอ'},
    'That is more replacement pieces than an order can take':
        {'th': 'จำนวนชิ้นงานทดแทนมากเกินกว่าที่ใบสั่งผลิตรับได้'},
    'This request does not exist or is not yours to answer.':
        {'th': 'ไม่พบคำขอนี้ หรือคุณไม่มีสิทธิ์ตอบคำขอนี้'},
    'This request was already answered. Refresh the list.':
        {'th': 'คำขอนี้ได้รับการตอบแล้ว กรุณาโหลดรายการใหม่'},

    # ------------------------------------------------------------------ manager alerts
    'Needs attention': {'th': 'ต้องดูแล'},
    'Needs attention ({n})': {'th': 'ต้องดูแล ({n})'},
    'Nothing needs attention right now.': {'th': 'ขณะนี้ไม่มีเรื่องที่ต้องดูแล'},
    '{order} is {days} days past its due date.': {'th': '{order} เลยวันครบกำหนดมา {days} วัน'},

    # ------------------------------------------------------ finish-time forecast
    'Expected finish': {'th': 'คาดว่าจะเสร็จ'},
    'Expected finish {when}': {'th': 'คาดว่าจะเสร็จ {when}'},
    ' · {n} days late': {'th': ' · ช้ากว่ากำหนด {n} วัน'},
    'Expected end': {'th': 'คาดว่าจะสิ้นสุด'},
    'Not available': {'th': 'ไม่มีข้อมูล'},
    'At risk': {'th': 'เสี่ยงล่าช้า'},
    '{order} is expected to finish {days} days after its due date.':
        {'th': '{order} คาดว่าจะเสร็จหลังวันครบกำหนด {days} วัน'},
    'Forecast from recent production at each step, in working hours.':
        {'th': 'พยากรณ์จากการผลิตล่าสุดของแต่ละขั้นตอน นับเฉพาะเวลาทำงาน'},
    'Forecast from standard step times, in working hours: too little history yet.':
        {'th': 'พยากรณ์จากเวลามาตรฐานของแต่ละขั้นตอน นับเฉพาะเวลาทำงาน เนื่องจากยังมีประวัติไม่พอ'},
    'Forecast from recent production where there is enough history, and standard step times elsewhere, in working hours.':
        {'th': 'พยากรณ์จากการผลิตล่าสุดในขั้นตอนที่มีประวัติพอ และใช้เวลามาตรฐานในขั้นตอนอื่น นับเฉพาะเวลาทำงาน'},
    'Expected end is a forecast in working hours (08:00–17:00, Monday to Friday, lunch break excluded), learned from recent production at each step and using the standard time where there is too little history.':
        {'th': 'คาดว่าจะสิ้นสุด คือค่าพยากรณ์ที่นับเฉพาะเวลาทำงาน (08:00–17:00 วันจันทร์ถึงศุกร์ ไม่รวมพักเที่ยง) '
               'เรียนรู้จากการผลิตล่าสุดของแต่ละขั้นตอน และใช้เวลามาตรฐานเมื่อมีประวัติไม่พอ'},
    '{quantity} pieces scrapped at {step} on {order}: {request}.':
        {'th': 'ของเสีย {quantity} ชิ้นที่ {step} ของ {order}: {request}'},
    '{step} on {order} has been paused for {minutes} minutes ({reason}).':
        {'th': '{step} ของ {order} หยุดมาแล้ว {minutes} นาที ({reason})'},
    '{quantity} pieces at {step} on {order} have run more than twice their standard time.':
        {'th': 'ชิ้นงาน {quantity} ชิ้นที่ {step} ของ {order} ใช้เวลาเกินสองเท่าของเวลามาตรฐาน'},
    'replacement pieces requested': {'th': 'ขอชิ้นงานทดแทน'},
    'review requested': {'th': 'ขอให้ตรวจสอบ'},
    'Scrap': {'th': 'ของเสีย'},
    'Long pause': {'th': 'หยุดนาน'},
    'Slow': {'th': 'ช้า'},
    ' · this week': {'th': ' · สัปดาห์นี้'},
    'All steps finished': {'th': 'ทุกขั้นตอนเสร็จแล้ว'},
    'Created': {'th': 'สร้างเมื่อ'},
    'Planned start': {'th': 'วันเริ่มตามแผน'},
    'Pieces finished per process step': {'th': 'ชิ้นงานที่เสร็จในแต่ละขั้นตอน'},
    'Pieces finished': {'th': 'ชิ้นงานที่เสร็จ'},
    'Start is the first piece started at the step; end is when its last piece finished. Elapsed '
    'time is clock time between them, including waiting between batches. Already-prepared '
    'pieces count as finished without processing time.':
        {'th': 'เวลาเริ่มคือเมื่อชิ้นแรกเริ่มในขั้นตอน เวลาสิ้นสุดคือเมื่อชิ้นสุดท้ายเสร็จ เวลาที่ใช้คือเวลาระหว่างสองจุดนี้ '
               'รวมการรอระหว่างรอบ ชิ้นที่เตรียมไว้แล้วนับว่าเสร็จโดยไม่มีเวลาดำเนินการ'},

    # ------------------------------------------------------------------- employment
    'Employment': {'th': 'การจ้างงาน'},
    'Marking someone as left disables their account, ends their unit assignments and hides them '
    'from selectors. Their record and history stay.':
        {'th': 'การบันทึกว่าลาออกจะปิดบัญชี สิ้นสุดการประจำหน่วยผลิต และซ่อนจากรายการให้เลือก ข้อมูลและประวัติยังคงอยู่'},
    'This person has left. Reinstating does not re-enable their account.':
        {'th': 'บุคคลนี้ลาออกแล้ว การรับกลับไม่ได้เปิดบัญชีให้อีกครั้ง'},
    'Mark as left': {'th': 'บันทึกว่าลาออก'},
    'Yes, mark as left': {'th': 'ใช่ บันทึกว่าลาออก'},
    'Reinstate': {'th': 'รับกลับเข้าทำงาน'},
    ' Show employees who have left': {'th': ' แสดงพนักงานที่ลาออกแล้ว'},
    'Left on {date}': {'th': 'ลาออกเมื่อ {date}'},
    'Marked as left': {'th': 'บันทึกว่าลาออก'},
    'Reinstated': {'th': 'รับกลับเข้าทำงาน'},
    'Their account will be disabled and their unit assignments will end now. Confirm to continue.':
        {'th': 'บัญชีจะถูกปิดและการประจำหน่วยผลิตจะสิ้นสุดทันที กรุณายืนยันเพื่อดำเนินการต่อ'},
    'Marked as left. Refresh the list to update it.': {'th': 'บันทึกว่าลาออกแล้ว กรุณาโหลดรายการใหม่'},
    'Reinstated. Enable their account when they need to sign in again.':
        {'th': 'รับกลับแล้ว เปิดบัญชีเมื่อต้องการให้เข้าสู่ระบบอีกครั้ง'},
    'You cannot mark the only Operations Administrator as left. Please, assign the role to '
    'another employee first.':
        {'th': 'คุณไม่สามารถบันทึกว่าผู้ดูแลงานปฏิบัติการคนเดียวลาออกได้ กรุณาให้บทบาทนี้แก่พนักงานคนอื่นก่อน'},
    'You cannot change your own employment here. Ask another administrator.':
        {'th': 'คุณไม่สามารถเปลี่ยนสถานะการจ้างงานของตนเองได้ กรุณาแจ้งผู้ดูแลระบบคนอื่น'},
    'This person is already marked as left.': {'th': 'บุคคลนี้ถูกบันทึกว่าลาออกแล้ว'},
    'This person has not left.': {'th': 'บุคคลนี้ยังไม่ได้ลาออก'},
    'This person has left. Reinstate them before enabling the account.':
        {'th': 'บุคคลนี้ลาออกแล้ว กรุณารับกลับก่อนเปิดบัญชี'},

    # ----------------------------------------------------------- order sheet and pauses
    'Print sheet with QR code': {'th': 'พิมพ์ใบงานพร้อมคิวอาร์โค้ด'},
    'Print': {'th': 'พิมพ์'},
    'Work order {number}': {'th': 'ใบสั่งผลิต {number}'},
    'QR code for work order {number}': {'th': 'คิวอาร์โค้ดของใบสั่งผลิต {number}'},
    'Scan to open this order on the supervisor page.':
        {'th': 'สแกนเพื่อเปิดใบสั่งผลิตนี้ในหน้าหัวหน้างาน'},
    '{n} executions were paused for {minutes} in total. Paused time is left out of active '
    'process time and over-standard figures, but never out of lead times or due dates.':
        {'th': 'การปฏิบัติงาน {n} รายการหยุดรวม {minutes} เวลาที่หยุดไม่นับในเวลาดำเนินการจริงและการเกินมาตรฐาน '
               'แต่ยังนับในระยะเวลาผลิตและวันครบกำหนดเสมอ'},
    '{reason}: {minutes} across {n} pauses': {'th': '{reason}: {minutes} จากการหยุด {n} ครั้ง'},
    # ------------------------------------------ units, history, paging and periods
    ' Show inactive units': {'th': ' แสดงหน่วยผลิตที่ไม่ได้ใช้งาน'},
    '+ Add production unit': {'th': '+ เพิ่มหน่วยผลิต'},
    'A unit with this name already exists at this location.': {'th': 'มีหน่วยผลิตชื่อนี้อยู่แล้วในสถานที่นี้'},
    'Activate': {'th': 'เปิดใช้งาน'},
    'Add unit': {'th': 'เพิ่มหน่วยผลิต'},
    'All time': {'th': 'ทั้งหมด'},
    'Between': {'th': 'ระหว่าง'},
    'Completed work orders, most recently completed first.': {'th': 'ใบสั่งผลิตที่เสร็จแล้ว เรียงจากที่เสร็จล่าสุดก่อน'},
    'Completed {date}': {'th': 'เสร็จเมื่อ {date}'},
    'Custom dates': {'th': 'กำหนดวันที่เอง'},
    'Deactivate': {'th': 'ปิดใช้งาน'},
    'Enter a name for the unit.': {'th': 'กรุณากรอกชื่อหน่วยผลิต'},
    'Every completed work order in the factory.': {'th': 'ใบสั่งผลิตที่เสร็จแล้วทั้งหมดในโรงงาน'},
    'Inactive': {'th': 'ไม่ได้ใช้งาน'},
    'Inactive units are hidden from the step editor and the supervisor list, but nothing that uses them is deleted: steps, orders and history keep them.': {'th': 'หน่วยผลิตที่ไม่ได้ใช้งานจะถูกซ่อนจากตัวแก้ไขขั้นตอนและรายการหัวหน้างาน แต่ไม่มีสิ่งใดที่ใช้หน่วยผลิตนั้นถูกลบ ขั้นตอน ใบสั่งผลิต และประวัติยังคงอยู่'},
    'Invalid page position. Reload the list.': {'th': 'ตำแหน่งหน้าไม่ถูกต้อง กรุณาโหลดรายการใหม่'},
    'Invalid page position. Reload the records.': {'th': 'ตำแหน่งหน้าไม่ถูกต้อง กรุณาโหลดรายการบันทึกใหม่'},
    'Last month': {'th': 'เดือนที่ผ่านมา'},
    'Last three months': {'th': 'สามเดือนที่ผ่านมา'},
    'Last week': {'th': 'สัปดาห์ที่ผ่านมา'},
    'Last year': {'th': 'ปีที่ผ่านมา'},
    'Late': {'th': 'ล่าช้า'},
    'Location': {'th': 'สถานที่'},
    'No completed work orders match these filters.': {'th': 'ไม่มีใบสั่งผลิตที่เสร็จแล้วตรงกับตัวกรองเหล่านี้'},
    'No location': {'th': 'ไม่ระบุสถานที่'},
    'No production units yet.': {'th': 'ยังไม่มีหน่วยผลิต'},
    'Nothing to show': {'th': 'ไม่มีข้อมูลที่จะแสดง'},
    'On time': {'th': 'ตรงเวลา'},
    'Only work orders with a step in a unit you supervise are shown.': {'th': 'แสดงเฉพาะใบสั่งผลิตที่มีขั้นตอนในหน่วยผลิตที่คุณดูแล'},
    'Order history': {'th': 'ประวัติใบสั่งผลิต'},
    'Process parts in your production units. Orders completed more than a month ago are in Order history.': {'th': 'งานในหน่วยผลิตของคุณ ใบสั่งผลิตที่เสร็จนานกว่าหนึ่งเดือนอยู่ในประวัติใบสั่งผลิต'},
    'Process reference code': {'th': 'รหัสอ้างอิงกระบวนการ'},
    'Production unit added.': {'th': 'เพิ่มหน่วยผลิตแล้ว'},
    'Production units': {'th': 'หน่วยผลิต'},
    'Reference codes are unique across every process and version. Leave it empty if not needed.': {'th': 'รหัสอ้างอิงต้องไม่ซ้ำกันในทุกกระบวนการและทุกเวอร์ชัน เว้นว่างไว้หากไม่ต้องการ'},
    'Reference codes are unique: version {version} keeps {code}, so a new version needs its own code or none.': {'th': 'รหัสอ้างอิงต้องไม่ซ้ำกัน เวอร์ชัน {version} ใช้รหัส {code} อยู่ เวอร์ชันใหม่จึงต้องมีรหัสของตัวเองหรือไม่มีรหัส'},
    'Search': {'th': 'ค้นหา'},
    'Showing {first}–{last}': {'th': 'แสดง {first}–{last}'},
    'That product or process reference code is already used.': {'th': 'รหัสอ้างอิงผลิตภัณฑ์หรือกระบวนการนี้ถูกใช้แล้ว'},
    'The date range ends before it starts': {'th': 'ช่วงวันที่สิ้นสุดก่อนวันเริ่มต้น'},
    'The history is unavailable. Retry shortly.': {'th': 'ไม่สามารถแสดงประวัติได้ กรุณาลองใหม่ในอีกสักครู่'},
    'This month': {'th': 'เดือนนี้'},
    'Unit activated.': {'th': 'เปิดใช้งานหน่วยผลิตแล้ว'},
    'Unit deactivated.': {'th': 'ปิดใช้งานหน่วยผลิตแล้ว'},
    'as of {time}': {'th': 'ณ เวลา {time}'},
    '{n} pieces': {'th': '{n} ชิ้น'},
}
