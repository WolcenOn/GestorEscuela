-- Esquema conceptual inicial. No se conecta todavía a la aplicación.
CREATE TABLE organizations (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE teachers (
    id TEXT NOT NULL,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    profile TEXT NOT NULL,
    substitution_count INTEGER NOT NULL DEFAULT 0 CHECK (substitution_count >= 0),
    emergency_only BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (organization_id, id)
);

CREATE TABLE groups (
    id TEXT NOT NULL,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    label TEXT NOT NULL,
    PRIMARY KEY (organization_id, id)
);

CREATE TABLE activities (
    id TEXT NOT NULL,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    activity_type TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    teacher_id TEXT NOT NULL,
    group_id TEXT,
    priority TEXT NOT NULL,
    movable BOOLEAN NOT NULL DEFAULT FALSE,
    cancelable BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (organization_id, id),
    FOREIGN KEY (organization_id, teacher_id) REFERENCES teachers(organization_id, id),
    FOREIGN KEY (organization_id, group_id) REFERENCES groups(organization_id, id)
);

CREATE TABLE absences (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    teacher_id TEXT NOT NULL,
    absence_date DATE NOT NULL,
    start_slot_id TEXT NOT NULL,
    end_slot_id TEXT NOT NULL,
    optional_reason TEXT,
    FOREIGN KEY (organization_id, teacher_id) REFERENCES teachers(organization_id, id)
);

CREATE INDEX idx_activities_org_slot ON activities (organization_id, slot_id);
CREATE INDEX idx_absences_org_date ON absences (organization_id, absence_date);
