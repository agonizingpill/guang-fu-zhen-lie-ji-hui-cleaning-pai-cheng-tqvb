from fastapi import APIRouter, Depends
from .database import session
from .auth import current, editor, admin
from .nozzle_schemas import (BatchInput, ReviewInput, VoidInput, IssueInput,
                             ReturnInput, ResolveInput, ReplacementInput)
from . import nozzle_service
router = APIRouter(prefix='/nozzles')


@router.get('/ledger')
def ledger(user=Depends(current), db=Depends(session)):
    return nozzle_service.ledger(db)


@router.get('/evidence')
def evidence(user=Depends(current)):
    from .nozzle_model import train_reference
    return train_reference()[1]


@router.post('/batches')
def batch(body: BatchInput, user=Depends(editor), db=Depends(session)):
    return nozzle_service.create_batch(db, body, user)


@router.post('/units/{key}/review')
def review(key: int, body: ReviewInput, user=Depends(admin), db=Depends(session)):
    return nozzle_service.review_unit(db, key, body, user)


@router.post('/batches/{key}/release')
def release(key: int, user=Depends(admin), db=Depends(session)):
    return nozzle_service.release(db, key, user)


@router.post('/batches/{key}/void')
def void(key: int, body: VoidInput, user=Depends(admin), db=Depends(session)):
    return nozzle_service.void_release(db, key, body, user)


@router.post('/issues')
def issue(body: IssueInput, user=Depends(editor), db=Depends(session)):
    return nozzle_service.issue(db, body, user)


@router.post('/returns')
def record_return(body: ReturnInput, user=Depends(editor), db=Depends(session)):
    return nozzle_service.record_return(db, body, user)


@router.post('/returns/{key}/resolve')
def resolve(key: int, body: ResolveInput, user=Depends(admin), db=Depends(session)):
    return nozzle_service.resolve_return(db, key, body, user)


@router.post('/replacements')
def replace(body: ReplacementInput, user=Depends(editor), db=Depends(session)):
    return nozzle_service.replacement(db, body, user)
