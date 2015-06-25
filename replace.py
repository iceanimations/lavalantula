import pymel.core as pc
import re
import maya.cmds as cmds
import os
import math
import json


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
            if basicName(sourceNode).startswith('group'):
                continue
            if isinstance(sourceNode, pc.nt.Constraint):
                continue
            if pc.nodeType(sourceNode) == 'joint':
                continue
            try:
                if pc.nodeType(sourceNode.getShape()) == 'mesh':
                    continue
            except:
                pass
            targetNode = getCorrespondingNode(sourceNode, targetRig,
                    sourceRig.namespace)

            if targetNode:
                self.copyAttrs(sourceNode, targetNode)
                copyKeyable(sourceNode, targetNode)

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


class SpiderRigReplacerUI(object):
    _ikPath = r"P:\external\Lavalantula\production\Rig\FINAL\lavalantula_RIG_v023_updated_Shd_v2.mb"
    _fkPath = r"P:\external\Lavalantula\production\Rig\FINAL\IK\lavalantula_RIG_FK_fix.mb"
    __file = os.path.join(os.path.expanduser('~'), 'lavalantula.json')

    def __init__(self):
        self.__retrieveRigPaths
        self.setupUi()
        self.populateRigs()

    def __retrieveRigPaths(self):
        data = {}
        try:
            with open(cls.__file) as rigf:
                data = json.load(rigf)
        except:
            pass
        if isinstance(data, dict):
            if data.has_key('ikPath'):
                self._ikPath = self.ikPath
            if data.has_key('fkPath'):
                self._fkPath = self.fkPath

    def __storeRigPaths(self):
        data = {}
        data['ikPath']=self._ikPath
        data['fkPath']=self._fkPath
        try:
            with open(self.__file, 'w+') as rigf:
                json.dump(data, rigf)
        except:
            pass

    def setupUi(self):
        ''' setup ui'''
        self.allSpiders = SpiderRig.getFromScene()
        with pc.window(title='Replace Lavalantula Rigs') as self.win:
            with pc.scrollLayout():
                with pc.columnLayout() as self.mainLayout:
                    self.ikrigField = pc.textFieldButtonGrp(label='IkRig:',
                            text=self._ikPath, bc=self.browseIk,
                            cw3 = (40, 360, 20), buttonLabel='...')
                    self.fkrigField = pc.textFieldButtonGrp(label='FkRig:',
                            text=self._fkPath, bc=self.browseFk,
                            cw3 = (40, 360, 20), buttonLabel='...')
                    pc.text(l='')
                    self.refreshBtn = pc.button('Refresh UI', width=420,
                            c=self.refreshAll)
                    pc.text('All Spider Rigs in the Scene')
                    with pc.rowLayout(nc=5):
                        pc.button('IK', width=30, c=self.selectIK)
                        pc.button('FK', width=30, c=self.selectFK)
                        pc.button('Ref', c=self.selectReferenced, width=30)
                        pc.button('Imp', c=self.selectImported, width=30)
                        pc.button('Select All', c=self.selectAll, width=300)
                    with pc.rowLayout(nc=3) as self.textListRowLayout:
                        self.rigTypeList = pc.textScrollList(
                                numberOfRows=len(self.allSpiders), width=60 )
                        self.referencedList = pc.textScrollList(
                                numberOfRows=len(self.allSpiders), width=60 )
                        self.selectionList = pc.textScrollList( ams=True, width=300,
                                numberOfRows=len(self.allSpiders) )
                    pc.text(l='')
                    pc.printSelectedBtn = pc.button('Replace Selected Items',
                        c=self.replaceSelectedItems, w=420)
                    pc.text(l='')
        self.selectionList.doubleClickCommand(self.selectSelected)
        self.rigTypeList.setEnable(False)
        self.referencedList.setEnable(False)

    def refreshAll(self, *args):
        self.allSpiders = SpiderRig.getFromScene()
        h = float(self.selectionList.getHeight()
                )/self.selectionList.getNumberOfItems()

        self.selectionList.removeAll()
        self.selectionList.setNumberOfRows(len(self.allSpiders))
        self.selectionList.setHeight(math.ceil(h*len(self.allSpiders)))

        self.referencedList.removeAll()
        self.referencedList.setNumberOfRows(len(self.allSpiders))
        self.referencedList.setHeight(math.ceil(h*len(self.allSpiders)))

        self.rigTypeList.removeAll()
        self.rigTypeList.setNumberOfRows(len(self.allSpiders))
        self.rigTypeList.setHeight(math.ceil(h*len(self.allSpiders)))

        self.populateRigs()

    def selectAll(self, *args):
        for idx in range(len(self.allSpiders)):
            self.selectionList.setSelectIndexedItem(idx+1)

    def selectIK(self, *args):
        self.selectionList.deselectAll()
        for idx, spider in enumerate(self.allSpiders):
            if spider.rigType() == SpiderRig.rigTypeIK:
                self.selectionList.setSelectIndexedItem(idx+1)

    def selectFK(self, *args):
        self.selectionList.deselectAll()
        for idx, spider in enumerate(self.allSpiders):
            if spider.rigType() == SpiderRig.rigTypeFK:
                self.selectionList.setSelectIndexedItem(idx+1)

    def selectReferenced(self, *args):
        self.selectionList.deselectAll()
        for idx, spider in enumerate(self.allSpiders):
            if spider.refNode:
                self.selectionList.setSelectIndexedItem(idx+1)

    def selectImported(self, *args):
        self.selectionList.deselectAll()
        for idx, spider in enumerate(self.allSpiders):
            if not spider.refNode:
                self.selectionList.setSelectIndexedItem(idx+1)

    def selectSelected(self, *args):
        pc.select(cl=True)
        for i in self.selectionList.getSelectIndexedItem():
            pc.select(self.allSpiders[i-1].rootNode, add=True)

    def populateRigs(self):
        self.selectionList.removeAll()
        self.referencedList.removeAll()
        self.rigTypeList.removeAll()
        for idx, spider in enumerate(self.allSpiders):
            self.referencedList.append('Yes' if spider.refNode else 'No')
            self.rigTypeList.append('IK' if spider.rigType() ==
                    SpiderRig.rigTypeIK else 'FK')
            self.selectionList.append(spider.rootNode.name())

    def getSelectedItems(self, *args):
        selected = []
        for i in self.selectionList.getSelectIndexedItem():
            selected.append(self.allSpiders[i-1])
        return selected

    def replaceSelectedItems(self, *args):
        srr = SpiderRigReplacer(self.getSelectedItems())
        ikPath = self.ikrigField.getText()
        fkPath = self.fkrigField.getText()
        srr.setRigPath(ikPath, SpiderRig.rigTypeIK)
        srr.setRigPath(fkPath, SpiderRig.rigTypeFK)
        srr.replaceAll()
        self._ikPath = ikPath
        self._fkPath = fkPath
        self.__storeRigPaths()
        self.refreshAll()

    def browseIk(self, *args):
        multipleFilters = "Maya Files (*.ma *.mb);;Maya ASCII (*.ma);;Maya Binary (*.mb)"
        startingDirectory = os.path.dirname(self.ikrigField.getText())
        result = pc.fileDialog2(fm=1, fileFilter=multipleFilters,
                cap='Select IK Rig File', startingDirectory=startingDirectory)
        if result:
            self.ikrigField.setText(result)

    def browseFk(self, *args):
        multipleFilters = "Maya Files (*.ma *.mb);;Maya ASCII (*.ma);;Maya Binary (*.mb)"
        startingDirectory = os.path.dirname(self.fkrigField.getText())
        result = pc.fileDialog2(fm=1, fileFilter=multipleFilters,
                cap='Select FK Rig File', startingDirectory=startingDirectory)
        if result:
            self.fkrigField.setText(result)

if __name__ == '__main__':
    #sr = SpiderRigReplacer()
    #sr.setRigPath(r"D:\talha.ahmed\workspace\mayaprojects\lavalantula\lavalantula_RIG_v023_proxy_withouttexture.mb")
    #sr.setRigPath(r"D:\talha.ahmed\workspace\mayaprojects\lavalantula\lavalantula_RIG_FK_fix_proxy.mb", 1)
    #sr.replaceAll()
    ui = SpiderRigReplacerUI()


