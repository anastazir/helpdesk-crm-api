import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.complaints.models import (
    Comment,
    Complaint,
    ComplaintAssignment,
    FileUpload,
    IssueType,
    JobNote,
    StatusHistory,
)
from apps.users.audit import log_user_event
from apps.users.models import User, UserAuditLog
from apps.zones.models import EngineerZoneAssignment, Zone

logger = logging.getLogger('seed')

MCD_ZONE_NAMES = [
    'Central Zone',
    'City-SP Zone',
    'Civil Lines Zone',
    'Karol Bagh Zone',
    'Keshavpuram Zone',
    'Najafgarh Zone',
    'Narela Zone',
    'Rohini Zone',
    'Shahdara North Zone',
    'Shahdara South Zone',
    'South Zone',
    'West Zone',
]

ISSUE_NAMES = [
    'System not working',
    'CPU FAN / CPU / PROCESSOR',
    'No power / SMPS Faulty',
    'Beep Sound / RAM issue',
    'HDD Faulty',
    'Mother Board Faulty',
    'Windows Corrupt / System Format',
    'Printer',
    'Monitor',
    'Networking',
    'Internet',
    'IP configuration',
    'Lan Driver',
    'Keyboard / Mouse issue',
    'Software Installation / Requirement of User',
    'Others',
]

USER_ROWS = [
    ('Admin User', 'admin@crm.in', '1234', 'admin', [], True),
    ('Supervisor One', 'supervisor@crm.in', '1234', 'supervisor', [], True),
    ('Priya Sharma', 'priya@crm.in', '1234', 'helpdesk', [], True),
    ('Meera Kapoor', 'meera@crm.in', '1234', 'helpdesk', [], True),
    ('Ravi Kumar', 'ravi@crm.in', '1234', 'engineer',
     ['Civil Lines Zone', 'Karol Bagh Zone'], True),
    ('Sandeep Rawat', 'sandeep@crm.in', '1234', 'engineer',
     ['Civil Lines Zone', 'Karol Bagh Zone'], True),
    ('Arjun Nambiar', 'arjun@crm.in', '1234', 'engineer',
     ['Keshavpuram Zone', 'Rohini Zone'], True),
    ('Anil Chauhan', 'anil@crm.in', '1234', 'engineer',
     ['Keshavpuram Zone', 'Rohini Zone'], True),
    ('Pooja Hegde', 'pooja@crm.in', '1234', 'engineer',
     ['Central Zone', 'City-SP Zone'], True),
    ('Nidhi Arora', 'nidhi@crm.in', '1234', 'engineer',
     ['Central Zone', 'City-SP Zone'], True),
    ('Kavita Menon', 'kavita@crm.in', '1234', 'engineer',
     ['Najafgarh Zone', 'West Zone'], True),
    ('Imran Qureshi', 'imran@crm.in', '1234', 'engineer',
     ['Najafgarh Zone', 'West Zone'], True),
    ('Rohit Bansal', 'rohit@crm.in', '1234', 'engineer',
     ['Narela Zone', 'Shahdara North Zone'], True),
    ('Harpreet Singh', 'harpreet@crm.in', '1234', 'engineer',
     ['Narela Zone', 'Shahdara North Zone'], True),
    ('Sneha Iyer', 'sneha@crm.in', '1234', 'engineer',
     ['Shahdara South Zone', 'South Zone'], True),
    ('Farah Khan', 'farah@crm.in', '1234', 'engineer',
     ['Shahdara South Zone', 'South Zone'], True),
    ('Deepak Verma', 'deepak@crm.in', '1234', 'engineer',
     ['Shahdara South Zone'], False),
]

CALLER_NAMES = [
    'Rajesh Kumar', 'Sunita Verma', 'Mohan Lal', 'Anjali Gupta', 'Vikram Singh',
    'Neha Sharma', 'Rakesh Yadav', 'Pooja Mehta', 'Sanjay Chauhan', 'Kavita Joshi',
    'Amit Saxena', 'Rekha Mishra', 'Suresh Rao', 'Nisha Bansal', 'Manoj Tiwari',
    'Shalini Dutta', 'Rajeev Menon', 'Preeti Kaur', 'Ashok Jain', 'Divya Nair',
    'Harish Patel', 'Swati Desai', 'Gaurav Bose', 'Ananya Reddy', 'Farhan Ali',
]

DEPARTMENTS = [
    'IT Department', 'Accounts', 'Administration', 'Public Works', 'Health',
]

DESIGNATIONS = [
    'Data Entry Operator', 'Clerk', 'Section Officer', 'Assistant Engineer',
    'Accountant', 'Computer Operator', 'Office Superintendent', 'Junior Assistant',
]

ADDRESSES = [
    'Room 204, Block C, Civil Lines',
    'Ground Floor, Zonal Office, Sector 12',
    'First Floor, Municipal Office, MG Road',
    'Room 18, District Office, Station Road',
    'Second Floor, Block A, Nehru Place',
    'Room 7, Sub-Divisional Office, Ring Road',
]

PINCODES = ['110054', '110001', '110002', '110003', '110006', '110009']

COMMENT_BODIES = [
    'Engineer has been notified and is on the way.',
    'Caller asked to be informed before the visit.',
    'Replacement part request noted. Awaiting stock.',
    'Service call report received. Verification pending.',
    'Complaint closed after document verification.',
]


class Command(BaseCommand):
    help = 'Seed the database with initial Help Desk CRM data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete all existing data before seeding.',
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            if options['flush']:
                self.flush()

            if self.has_data():
                self.stdout.write(
                    '[SEED] Existing data found. Skipping seeding. '
                    'Use --flush to reset.'
                )
                return

            self.seed()

    def has_data(self):
        return (
            User.objects.filter(is_superuser=False).exists()
            or Zone.objects.exists()
            or IssueType.objects.exists()
            or Complaint.objects.exists()
        )

    def flush(self):
        FileUpload.objects.all().delete()
        Comment.objects.all().delete()
        JobNote.objects.all().delete()
        StatusHistory.objects.all().delete()
        ComplaintAssignment.objects.all().delete()
        Complaint.objects.all().delete()
        EngineerZoneAssignment.objects.all().delete()
        Zone.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        IssueType.objects.all().delete()
        self.stdout.write('[SEED] Existing data flushed.')

    def seed(self):
        self.stdout.write('[SEED] Creating zones...', ending='')
        zones = {}
        for zone_name in MCD_ZONE_NAMES:
            zones[zone_name] = Zone.objects.create(name=zone_name)
        self.stdout.write(f' done ({len(zones)})')

        self.stdout.write('[SEED] Creating issue types...', ending='')
        issues = []
        for order, issue_name in enumerate(ISSUE_NAMES, start=1):
            issues.append(IssueType.objects.create(name=issue_name, order=order))
        self.stdout.write(f' done ({len(issues)})')

        self.stdout.write('[SEED] Creating users...', ending='')
        users = {}
        for row_index, (full_name, email, password, role, zone_names, is_active) in enumerate(USER_ROWS, start=1):
            phone = str(9000000000 + row_index)
            existing = User.objects.filter(email=email).first()
            if existing is not None:
                existing.full_name = full_name
                existing.role = role
                existing.phone = phone
                existing.is_active = is_active
                existing.is_staff = role == 'admin' or existing.is_superuser
                if not existing.is_superuser:
                    existing.set_password(password)
                existing.save()
                user = existing
            else:
                extra_fields = {
                    'full_name': full_name,
                    'role': role,
                    'phone': phone,
                    'is_active': is_active,
                    'is_staff': role == 'admin',
                }
                user = User.objects.create_user(
                    email=email, password=password, **extra_fields
                )
            users[email] = user

            for zone_name in zone_names:
                EngineerZoneAssignment.objects.create(
                    engineer=user,
                    zone=zones[zone_name],
                    action='added',
                    changed_by=users['admin@crm.in'],
                )

        for zone in zones.values():
            zone.created_by = users['admin@crm.in']
            zone.save(update_fields=['created_by'])

        admin = users['admin@crm.in']
        for email, user in users.items():
            if email == 'admin@crm.in':
                continue
            user.created_by = admin
            user.save(update_fields=['created_by'])

        for user in users.values():
            if UserAuditLog.objects.filter(
                target=user, action='created', source='backfill'
            ).exists():
                continue
            log_user_event(
                action='created',
                actor=None if user == admin else admin,
                target=user,
                changes={'created': {'old': None, 'new': user.role}},
                source='backfill',
                note='Seed account creation.',
            )

        self.stdout.write(f' done ({len(users)})')

        self.stdout.write('[SEED] Creating complaints...', ending='')
        complaints = self.create_complaints(users, zones, issues)
        self.stdout.write(f' done ({len(complaints)})')

        self.stdout.write('[SEED] Seed complete.')

    def create_complaints(self, users, zones, issues):
        hd_users = [users['priya@crm.in'], users['meera@crm.in']]
        engineers = [
            users['ravi@crm.in'],
            users['arjun@crm.in'],
            users['pooja@crm.in'],
        ]
        zone_list = [zones[name] for name in MCD_ZONE_NAMES]
        zone_engineers = {zone.name: [] for zone in zone_list}
        for _, email, _, role, zone_names, is_active in USER_ROWS:
            if role != 'engineer' or not is_active:
                continue
            for zone_name in zone_names:
                zone_engineers[zone_name].append(users[email])

        status_plan = (
            ['open'] * 5
            + ['assigned'] * 5
            + ['in_progress'] * 5
            + ['parts_requested']
            + ['parts_provided']
            + ['resolved'] * 3
            + ['closed'] * 5
        )

        complaints = []
        for index, target_status in enumerate(status_plan):
            creator = hd_users[index % len(hd_users)]
            zone = zone_list[index % len(zone_list)]
            zone_engineer_pool = zone_engineers[zone.name]
            engineer = zone_engineer_pool[index % len(zone_engineer_pool)]
            issue = issues[index % (len(issues) - 1)]

            complaint = Complaint.objects.create(
                caller_phone=f'98765432{index:02d}',
                caller_name=CALLER_NAMES[index],
                bmid=f'BM-{20000 + index}',
                aadhaar=None,
                zone=zone,
                department=DEPARTMENTS[index % len(DEPARTMENTS)],
                designation=DESIGNATIONS[index % len(DESIGNATIONS)],
                address=ADDRESSES[index % len(ADDRESSES)],
                pincode=PINCODES[index % len(PINCODES)],
                cpu_serial=f'SN-CPU-{1000 + index}',
                monitor_serial=f'SN-MON-{2000 + index}',
                status='open',
                created_by=creator,
            )
            complaint.issues.set([issue, issues[(index + 5) % (len(issues) - 1)]])

            StatusHistory.objects.create(
                complaint=complaint,
                previous_status=None,
                new_status='open',
                changed_by=creator,
            )

            if target_status != 'open':
                ComplaintAssignment.objects.create(
                    complaint=complaint,
                    engineer=engineer,
                    assigned_by=creator,
                )
                StatusHistory.objects.create(
                    complaint=complaint,
                    previous_status='open',
                    new_status='assigned',
                    changed_by=creator,
                )
                complaint.status = 'assigned'
                complaint.save(update_fields=['status'])

            if target_status in [
                'in_progress', 'parts_requested', 'parts_provided', 'resolved', 'closed'
            ]:
                StatusHistory.objects.create(
                    complaint=complaint,
                    previous_status='assigned',
                    new_status='in_progress',
                    changed_by=creator,
                )
                complaint.status = 'in_progress'
                complaint.save(update_fields=['status'])

            if target_status in ['parts_requested', 'parts_provided']:
                JobNote.objects.create(
                    complaint=complaint,
                    text='Replacement part required to complete the repair.',
                    created_by=engineer,
                )
                StatusHistory.objects.create(
                    complaint=complaint,
                    previous_status='in_progress',
                    new_status='parts_requested',
                    changed_by=engineer,
                )
                complaint.status = 'parts_requested'
                complaint.save(update_fields=['status'])

            if target_status == 'parts_provided':
                StatusHistory.objects.create(
                    complaint=complaint,
                    previous_status='parts_requested',
                    new_status='parts_provided',
                    changed_by=creator,
                )
                complaint.status = 'parts_provided'
                complaint.save(update_fields=['status'])

            if target_status in ['resolved', 'closed']:
                StatusHistory.objects.create(
                    complaint=complaint,
                    previous_status='in_progress',
                    new_status='resolved',
                    changed_by=engineer,
                )
                complaint.status = 'resolved'
                complaint.save(update_fields=['status'])

            if target_status == 'closed':
                StatusHistory.objects.create(
                    complaint=complaint,
                    previous_status='resolved',
                    new_status='closed',
                    changed_by=creator,
                )
                complaint.status = 'closed'
                complaint.save(update_fields=['status'])

            complaints.append(complaint)

        comment_indexes = [5, 6, 10, 15, 16]
        comment_authors = [hd_users[0], hd_users[1], engineers[0]]
        for position, complaint_index in enumerate(comment_indexes):
            Comment.objects.create(
                complaint=complaints[complaint_index],
                author=comment_authors[position % len(comment_authors)],
                body=COMMENT_BODIES[position % len(COMMENT_BODIES)],
            )

        self.backdate_complaints(complaints)
        return complaints

    def backdate_complaints(self, complaints):
        now = timezone.now()

        for index, complaint in enumerate(complaints):
            age_days = index % 18
            age_hours = (index * 5) % 24
            created_at = now - timedelta(
                days=age_days,
                hours=age_hours,
                minutes=(index * 7) % 60,
            )
            Complaint.objects.filter(pk=complaint.pk).update(created_at=created_at)

            entries = list(complaint.status_history.order_by('id'))
            for position, entry in enumerate(entries):
                event_time = created_at + timedelta(hours=position * 4)
                if event_time >= now - timedelta(minutes=5):
                    event_time = now - timedelta(minutes=(len(entries) - position) * 5)
                StatusHistory.objects.filter(pk=entry.pk).update(changed_at=event_time)

            if complaint.status == 'closed':
                closed_entry = complaint.status_history.filter(
                    new_status='closed'
                ).order_by('-changed_at').first()
                if closed_entry:
                    StatusHistory.objects.filter(pk=closed_entry.pk).update(
                        changed_at=now - timedelta(minutes=30 + index)
                    )
