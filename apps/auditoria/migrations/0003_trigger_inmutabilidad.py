from django.db import migrations

def aplicar_trigger_segun_motor(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == 'postgresql':
            cursor.execute("""
                CREATE OR REPLACE FUNCTION bloquear_modificacion_auditoria()
                RETURNS TRIGGER AS $$
                BEGIN
                    RAISE EXCEPTION 'VIOLACIÓN DE AUDITORÍA: Los registros contables en % son estrictamente inmutables y no admiten UPDATE ni DELETE.', TG_TABLE_NAME;
                    RETURN NULL;
                END;
                $$ LANGUAGE plpgsql;

                DROP TRIGGER IF EXISTS trg_proteger_auditoria_contable ON auditoria_logauditoriacontable;
                CREATE TRIGGER trg_proteger_auditoria_contable
                BEFORE UPDATE OR DELETE ON auditoria_logauditoriacontable
                FOR EACH ROW
                EXECUTE FUNCTION bloquear_modificacion_auditoria();
            """)
        elif vendor == 'sqlite':
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_bloquear_update_auditoria
                BEFORE UPDATE ON auditoria_logauditoriacontable
                BEGIN
                    SELECT RAISE(ABORT, 'VIOLACIÓN DE AUDITORÍA: Los registros son inmutables.');
                END;
            """)
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_bloquear_delete_auditoria
                BEFORE DELETE ON auditoria_logauditoriacontable
                BEGIN
                    SELECT RAISE(ABORT, 'VIOLACIÓN DE AUDITORÍA: Los registros son inmutables.');
                END;
            """)


def revertir_trigger(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == 'postgresql':
            cursor.execute("""
                DROP TRIGGER IF EXISTS trg_proteger_auditoria_contable ON auditoria_logauditoriacontable;
                DROP FUNCTION IF EXISTS bloquear_modificacion_auditoria();
            """)
        elif vendor == 'sqlite':
            cursor.execute("DROP TRIGGER IF EXISTS trg_bloquear_update_auditoria;")
            cursor.execute("DROP TRIGGER IF EXISTS trg_bloquear_delete_auditoria;")


class Migration(migrations.Migration):
    dependencies = [
        ('auditoria', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(
            aplicar_trigger_segun_motor,
            reverse_code=revertir_trigger
        ),
    ]
