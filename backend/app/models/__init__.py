"""Import all models so SQLAlchemy metadata and Alembic see every table."""
from app.models.ai import (  # noqa: F401
    AIProvider,
    AIModel,
    AIUsageLog,
    Document,
    DocumentChunk,
    GeneratedContent,
    TutorConversation,
    TutorMessage,
)
from app.models.assessment import (  # noqa: F401
    Assessment,
    AssessmentQuestion,
    AssessmentResult,
    Question,
    QuestionOption,
    StudentAnswer,
    StudentAttempt,
)
from app.models.core import (  # noqa: F401
    AcademicYear,
    AuditLog,
    Role,
    School,
    Semester,
    Session,
    User,
)
from app.models.intelligence import (  # noqa: F401
    AdaptivePractice,
    BktHistory,
    EngineConfig,
    LearningRecommendation,
    RemedialRecord,
    StudentCompetencyMastery,
    StudentNote,
)
from app.models.academic import (  # noqa: F401
    Class,
    ClassMember,
    Competency,
    LearningMaterial,
    LearningObjective,
    Subject,
    TeacherClass,
)
from app.models.operations import (  # noqa: F401
    DeletionRequest,
    SecretRotation,
    SyncConflict,
)
