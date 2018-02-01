from flask import current_app as capp
from flask import jsonify, g
from fence.data_model.models import ResearchGroup, AccessPrivilege


def find_group(group_id, session):
    group = session.query(ResearchGroup).filter(ResearchGroup.id == group_id).first()
    if not group:
        raise NotFound("group {} not found".format(group_id))
    return group


def get_group_id(group_id):

    group_info = dict()
    with capp.db.session as session:
        group = session.query(ResearchGroup).filter(ResearchGroup.id == group_id).first()

        if group is not None:
            group_info["group_id"] = group.id
            group_info["group_name"] = group.name
            group_info["lead_id"] = group.lead_id
    return jsonify(group_info)


def get_all_groups_info():

    all_info = list()

    with capp.db.session as session:
        groups = session.query(ResearchGroup).all()

        for group in groups:
            print group
            all_info.append({'group_id': group.id,
                             'group_name': group.name,
                             'lead_id': group.lead_id
                             })

    return jsonify({"results": all_info})


def get_projects_by_group(group_id):

    projects = list()

    with capp.db.session as session:
        access_privileges = session.query(AccessPrivilege).\
            filter(AccessPrivilege.group_id == group_id).all()

        for access_privilege in access_privileges:
            projects.append({
                "project_id": access_privilege.project_id,
                "privilege": access_privilege.privilege
            })

    return jsonify({"result": projects})
