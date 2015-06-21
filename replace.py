import pymel.core as pc
import re
import maya.cmds as cmds
import os


def basicName(node):
    return node.name().split('|')[-1].split(':')[-1]

def getCorrespondingNode(sourcenode, targetRig, sourceNamespace=''):
    sourceComps = sourcenode.fullPath().split('|')
    targetComps = []
    basefound = False
    for comp in sourceComps:
        if SpiderRig.pattern.match(comp):
            basefound = True
        if basefound:
            targetComps.append(comp)
    if sourceNamespace:
        targetComps = [comp.replace(sourceNamespace, '', 1)
                if comp.startswith(sourceNamespace) else comp
                for comp in targetComps]
    targetComps[0] = basicName(targetRig.rootNode)
    targetNamespace = pc.referenceQuery(targetRig.refNode, namespace=True,
            shortName=True)
    targetComps = [targetNamespace + ":" + comp for comp in targetComps]

    result = None
    try:
        result = pc.PyNode('|'.join(targetComps))
    except Exception as e:
        pass
        #print '|'.join(targetComps), e
    return result

def copyKeyable(sourceNode, targetNode):
    '''
    :type sourceNode: pymel.core.nodetypes.DependNode
    :type targetNode: pymel.core.nodetypes.DependNode
    '''
    for attr in sourceNode.listAttr(keyable=True):
        try:
            val = attr.get()
            targetNode.attr(attr.attrName()).set(val)
        except Exception as e:
            pass
            #print e, attr, targetNode


class SpiderRig(object):
    pattern = re.compile('(.*:)?LAVALANTULA_RIG_NUL_\d+')
    rigTypeIK=0
    rigTypeFK=1

    __refNode = None

    def __init__(self, transform):
        '''
        :type transform: pymel.core.nodetypes.Transform()
        '''
        if SpiderRig.isSpiderRig(transform):
            self.rootNode = pc.PyNode(transform)
            self.namespace = self.rootNode.namespace()
        else:
            raise TypeError, 'not a valid SpiderRig baseNode'

    def __hash__(self):
        return hash(self.rootNode)

    def __determineRefNode(self):
        refnodes = pc.ls(type='reference')
        for node in refnodes:
            nodelist = []
            ref = pc.FileReference(node)
            try:
                nodelist = ref.nodes()
            except:
                pass
            if self.rootNode in nodelist:
                self.__refNode = node
        if self.__refNode is None:
            self.__refNode = False

    @staticmethod
    def getFromScene():
        '''
        :rtype: `list of SpiderRig`
        '''
        transforms = pc.ls(type='transform')
        return [SpiderRig(node) for node in transforms if SpiderRig.isSpiderRig(node)]

    @staticmethod
    def getFromList(thislist=None, seekParents=False):
        def ancestors(node):
            parent = None
            if hasattr(node, 'firstParent2'):
                parent = node.firstParent2()
            else:
                return []
            if not parent:
                return [node]
            else:
                parents = ancestors(parent)
                parents.append(node)
                return parents

        rigs = set()

        if thislist is None:
            thislist = pc.ls(sl=1)

        for node in thislist:
            seek = [node]
            if seekParents:
                seek = ancestors(node)
            for parent in seek:
                if SpiderRig.isSpiderRig(parent):
                    rigs.add(SpiderRig(parent))

        return list(rigs)

    def rigType(self):
        name = 'legFront_IK_R_JNT_5'
        joints = self.rootNode.getChildren(ad=True, type='joint')
        for joint in joints:
            if basicName(joint) == name:
                break
        if len(joint.getChildren()) == 3:
            return SpiderRig.rigTypeIK
        else:
            return SpiderRig.rigTypeFK

    def isComplete(self):
        return self.rootNode.getChildren(ad=True) == 1077

    @staticmethod
    def isSpiderRig(candidate):
        if not isinstance(candidate, pc.nt.DependNode) and isinstance(candidate, basestring):
            candidate = pc.PyNode(candidate)
        if not isinstance(candidate, pc.nt.Transform):
            return False
        if not SpiderRig.pattern.match(basicName(candidate)):
            return False
        return True

    def getRefNode(self):
        if self.__refNode is None:
            self.__determineRefNode()
        return self.__refNode
    def setRefNode(self, refNode):
        self.__refNode = refNode
    refNode = property(getRefNode, setRefNode)

    def __repr__(self):
        return repr(self.rootNode)



class SpiderRigReplacer(object):
    __fkrig = None
    __ikrig = None
    __attrForCopy = [
            "rotatePivotX",
            "rotatePivotY",
            "rotatePivotZ",
            "rotatePivotTranslateX",
            "rotatePivotTranslateY",
            "rotatePivotTranslateZ",
            "scalePivotX",
            "scalePivotY",
            "scalePivotZ",
            "scalePivotTranslateX",
            "scalePivotTranslateY",
            "scalePivotTranslateZ",
            "translateX",
            "translateY",
            "translateZ",
            "rotateX",
            "rotateY",
            "rotateZ",
            "scaleX",
            "scaleY",
            "scaleZ",
    ]

    def __init__(self, spiders=None):
        self.sourceRigs = spiders
        if self.sourceRigs is None:
            self.sourceRigs = [rig for rig in SpiderRig.getFromScene() if not rig.refNode]
        self.targetRigs = dict()

    def replaceAll(self):
        for sourceRig in self.sourceRigs:
            self.replace(sourceRig)

    def replace(self, sourceRig):
        '''
        :type sourceRig: SpiderRig
        '''
        targetRig = self.referenceRig(sourceRig.rigType())
        parent = sourceRig.rootNode.firstParent2()
        if parent:
            pc.parent(targetRig.rootNode, parent, r=True)
        allthings = [sourceRig.rootNode] + sourceRig.rootNode.getChildren(ad=True)

        for sourceNode in allthings:
            targetNode = None
            targetNode = getCorrespondingNode(sourceNode, targetRig,
                    sourceRig.namespace)

            if targetNode:
                self.copyAttrs(sourceNode, targetNode)
                if pc.copyKey(sourceNode):
                    #copyKeyable(sourceNode, targetNode)
                    pc.pasteKey(targetNode)

        self.targetRigs[sourceRig]=targetRig

    def copyAttrs(self, sourceNode, targetNode):
        for attr in self.__attrForCopy:
            try:
                val = sourceNode.attr(attr).get()
                targetNode.attr(attr).set(val)
            except Exception as e:
                pass
                #print e, attr

    def referenceRig(self, rigType):
        path = self.__fkrig if rigType == SpiderRig.rigTypeFK else self.__ikrig
        if path is None:
            raise ValueError, 'Correct rigtype is not specified'
        namespace = os.path.basename(path)
        namespace = os.path.splitext(namespace)[0]
        newnodes = cmds.file(path, r=True, mnc=False, namespace=namespace, rnn=True)

        refNode = None
        for nodename in newnodes:
            if cmds.nodeType(nodename) == 'reference':
                refNode = pc.PyNode(cmds.referenceQuery(nodename,
                    referenceNode=True, topReference=True))

        newrig = SpiderRig.getFromList(newnodes)[0]
        newrig.refNode = refNode
        return newrig


    def setRigPath(self, rig, rigType=SpiderRig.rigTypeIK):
        if os.path.exists(rig) and os.path.isfile(rig) and (rig.endswith('ma')
                or rig.endswith('mb')):

            if rigType == SpiderRig.rigTypeIK:
                self.__ikrig = rig
            else:
                self.__fkrig = rig
        else:
            raise ValueError, 'Invalid Rig Path'

    def getRigPath(self, rigType=SpiderRig.rigTypeIK):
        if rigType == SpiderRig.rigTypeIK:
            return self.__ikrig
        else:
            return self.__fkrig


if __name__ == '__main__':
    sr = SpiderRigReplacer()
    sr.setRigPath(r"D:\talha.ahmed\workspace\mayaprojects\lavalantula\lavalantula_RIG_v023_proxy_withouttexture.mb")
    sr.setRigPath(r"D:\talha.ahmed\workspace\mayaprojects\lavalantula\lavalantula_RIG_FK_fix_proxy.mb", 1)
    sr.replaceAll()
